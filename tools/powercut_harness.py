"""Process-kill durability harness (verification of REQ-DAT-002, test F-01).

Each cycle starts a writer that appends records as fast as it can and prints
the sequence number of every record *after* append() returns (i.e. after all
three copies are fsynced). The harness SIGKILLs the writer at a random moment,
runs recovery, and checks:

  * every acknowledged record survived              (no committed data lost)
  * at most one unacknowledged record was kept      (only the in-flight write)
  * the chain is intact and every copy is identical (no corruption)

Limits, stated plainly: SIGKILL stops the process but the OS page cache
survives, so this does not prove behaviour under true power loss. The relay
rig in deploy/pico/ cuts real power for that.

usage: python3 tools/powercut_harness.py --cycles 1000 --dir /tmp/lsst-kill
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "service"))
from lsst_service.eventlog import EventLog, read_text  # noqa: E402


def paths(d):
    return [os.path.join(d, f"log.{c}") for c in "ABC"], os.path.join(d, "state")


def child(d):
    copies, state = paths(d)
    log = EventLog(copies, state)
    log.recover()
    out = sys.stdout
    while True:
        rec = log.append("rec", {"item": "kill-test", "n": random.randrange(10**9)})
        out.write(f"{rec['seq']}\n")
        out.flush()


def one_cycle(d, rng, prev_last: int) -> dict:
    proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--child", d],
                            stdout=subprocess.PIPE, text=True)
    time.sleep(rng.uniform(0.02, 0.15))
    proc.send_signal(signal.SIGKILL)
    out, _ = proc.communicate()
    acked = [int(x) for x in out.split() if x.isdigit()]
    copies, state = paths(d)
    log = EventLog(copies, state)
    rep = log.recover()
    last = log.records[-1]["seq"] if log.records else 0
    floor = max([prev_last] + acked)   # everything acknowledged so far must survive
    texts = {read_text(p) for p in copies}
    ok = (floor <= last <= floor + 1
          and rep.chain_breaks == 0 and not rep.unrecoverable and len(texts) == 1
          and [r["seq"] for r in log.records] == list(range(1, last + 1)))
    return {"ok": ok, "acked": floor, "recovered": last, "repaired": rep.repaired,
            "uncommitted": rep.uncommitted, "torn": rep.torn}


def run(cycles: int, d: str, seed: int = 7, quiet: bool = False) -> dict:
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    rng = random.Random(seed)
    fails, torn, repaired, last = [], 0, 0, 0
    t0 = time.time()
    for i in range(cycles):
        r = one_cycle(d, rng, last)
        last = r["recovered"]
        torn += r["torn"] > 0
        repaired += r["repaired"] > 0
        if not r["ok"]:
            fails.append((i, r))
        if not quiet and (i + 1) % 50 == 0:
            print(f"  {i + 1}/{cycles} cycles, {len(fails)} failures", flush=True)
    return {"cycles": cycles, "failures": len(fails), "first_failures": fails[:3],
            "cycles_with_torn_tail": torn, "cycles_needing_repair": repaired,
            "records_at_end": r["recovered"], "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", type=int, default=200)
    ap.add_argument("--dir", default=os.path.join(ROOT, "data", "killtest"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    res = run(a.cycles, a.dir, a.seed)
    print(res)
    sys.exit(1 if res["failures"] else 0)
