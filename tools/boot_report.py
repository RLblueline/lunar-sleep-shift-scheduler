"""Summarize boot records from the event log (evidence for F-01R, the power-cut rig).

usage: python3 tools/boot_report.py [log copy paths...]
Defaults to the paths in LSST_LOG_COPIES or ./data/log.{A,B,C}.
"""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "service"))
from lsst_service.config import Config  # noqa: E402
from lsst_service.eventlog import EventLog  # noqa: E402


def main(argv):
    cfg = Config()
    copies = argv or cfg.log_copies
    log = EventLog(copies, cfg.state_dir)
    rep = log.recover()
    boots = [r["payload"] for r in log.records if r["type"] == "boot"]
    status = collections.Counter(b.get("status") for b in boots)
    print(f"records: {rep.total}   boots logged: {len(boots)}")
    for k in ("NOMINAL", "DEGRADED", "SAFE"):
        print(f"  {k:9s} {status.get(k, 0)}")
    print(f"  boots that repaired at least one copy: {sum(1 for b in boots if b.get('repaired'))}")
    print(f"  boots that reported lost records:      {sum(1 for b in boots if b.get('unrec'))}")
    print(f"recovery now: {rep.as_dict()}")


if __name__ == "__main__":
    main(sys.argv[1:])
