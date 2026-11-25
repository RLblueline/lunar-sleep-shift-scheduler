"""Data service verification. Test names carry the requirement ID they verify (tools/trace.py reads them)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "service"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lsst_service.config import Config  # noqa: E402
from lsst_service.eventlog import EventLog, make_line, parse_line, read_text  # noqa: E402
from lsst_service.hardware.lights import MODES, SimulatedLights, mix  # noqa: E402
from lsst_service.server import Service, make_handler  # noqa: E402
import powercut_harness  # noqa: E402


def fresh_log(tmp):
    return EventLog([os.path.join(tmp, f"log.{c}") for c in "ABC"], os.path.join(tmp, "state"))


def seeded(tmp, n=20):
    log = fresh_log(tmp)
    log.recover()
    for i in range(n):
        log.append("rec", {"i": i, "note": "seed"})
    return log


class EventLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lsst-test-")

    def test_REQ_DAT_001_records_are_checksummed_and_hash_chained(self):
        log = seeded(self.tmp, 5)
        prev = "00000000"
        for r in log.records:
            self.assertEqual(r["prev"], prev)
            prev = r["crc"]
        bad = log.records[2]["line"].replace('"i":2', '"i":3')
        self.assertIsNone(parse_line(bad), "a changed record must fail its checksum")

    def test_REQ_DAT_002_append_returns_only_after_all_copies_hold_the_record(self):
        log = seeded(self.tmp, 3)
        rec = log.append("rec", {"x": 1})
        for p in log.paths:
            self.assertTrue(read_text(p).endswith(rec["line"] + "\n"))

    def test_REQ_DAT_002_kill9_never_loses_an_acknowledged_record(self):
        res = powercut_harness.run(30, os.path.join(self.tmp, "kill"), seed=11, quiet=True)
        self.assertEqual(res["failures"], 0, res["first_failures"])

    def test_REQ_DAT_003_single_copy_bit_flip_is_repaired_by_vote(self):
        log = seeded(self.tmp)
        before = read_text(log.paths[0])
        log.corrupt(1, 7)
        log2 = fresh_log(self.tmp)
        rep = log2.recover()
        self.assertEqual(rep.corrupt, 1)
        self.assertEqual(rep.repaired, 1)
        self.assertEqual(len(log2.records), 20)
        for p in log2.paths:
            self.assertEqual(read_text(p), before)

    def test_REQ_DAT_003_two_copy_bit_flip_recovers_from_the_last_good_copy(self):
        log = seeded(self.tmp)
        log.corrupt(0, 9)
        log.corrupt(2, 9)
        rep = fresh_log(self.tmp).recover()
        self.assertEqual(rep.total, 20)
        self.assertEqual(rep.unrecoverable, [])

    def test_REQ_DAT_004_record_lost_in_every_copy_is_reported_not_hidden(self):
        log = seeded(self.tmp)
        for c in range(3):
            log.corrupt(c, 4)
        log2 = fresh_log(self.tmp)
        rep = log2.recover()
        self.assertEqual(rep.unrecoverable, [5])
        self.assertEqual(rep.total, 19)
        rec = log2.append("rec", {"after": "loss"})  # the log keeps working
        self.assertEqual(rec["seq"], 21)

    def test_REQ_DAT_005_torn_write_is_dropped_and_appends_continue(self):
        log = seeded(self.tmp)
        log.torn_append("rec", {"inflight": True})
        log2 = fresh_log(self.tmp)
        rep = log2.recover()
        self.assertEqual(rep.uncommitted, 1)
        self.assertEqual(rep.total, 20)
        rec = log2.append("rec", {"next": True})
        self.assertEqual(rec["seq"], 21)
        self.assertEqual(fresh_log(self.tmp).recover().total, 21)

    def test_REQ_DAT_006_snapshot_falls_back_to_the_other_slot(self):
        log = seeded(self.tmp)
        log.write_snapshot(10, "aaaa")
        log.write_snapshot(20, "bbbb")
        self.assertEqual(log.read_snapshot()["pick"]["seq"], 20)
        log.corrupt_snapshot()
        snap = log.read_snapshot()
        self.assertFalse(snap["ptrValid"])
        self.assertEqual(snap["pick"]["seq"], 10)

    def test_REQ_DAT_007_total_wipe_leaves_an_empty_valid_log(self):
        log = seeded(self.tmp)
        log.wipe()
        log2 = fresh_log(self.tmp)
        self.assertEqual(log2.recover().total, 0)
        self.assertEqual(log2.append("genesis", {})["seq"], 1)


class CrossLanguageTests(unittest.TestCase):
    def test_REQ_VER_003_service_records_verify_in_the_ui_checksum_code(self):
        lines = [make_line(1, "crew", {"id": "cdr", "name": "R. Okafor", "tau": 24.15, "need": 7.5}, "00000000"),
                 make_line(2, "rec", {"note": "unicode é ✓", "n": 0.30000000000000004, "neg": -4}, "abcd1234"),
                 make_line(3, "power", {"event": "low-battery-shutdown", "pct": 5.0, "volts": 3.3}, "0badf00d")]
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "verify_lines.js")],
                             input="\n".join(lines), capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "3/3 valid")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lsst-svc-")
        os.environ["LSST_DATA"] = self.tmp

    def start(self, **kw):
        cfg = Config(port=0, web_root=os.path.join(ROOT, "web", "dist"), **kw)
        cfg.log_copies = [os.path.join(self.tmp, f"log.{c}") for c in "ABC"]
        cfg.state_dir = os.path.join(self.tmp, "state")
        httpd = HTTPServer(("127.0.0.1", 0), make_handler(Service(cfg)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    @staticmethod
    def post(url, body):
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_REQ_OPS_002_service_binds_to_localhost_by_default(self):
        os.environ.pop("LSST_HOST", None)
        self.assertEqual(Config().host, "127.0.0.1")

    def test_REQ_DAT_002_api_append_is_durable_before_response(self):
        base = self.start()
        st, out = self.post(base + "/api/append", {"type": "rec", "payload": {"a": 1}})
        self.assertEqual(st, 200)
        self.assertIn(out["line"] + "\n", read_text(os.path.join(self.tmp, "log.C")))

    def test_REQ_SAF_003_fault_injection_can_be_disabled(self):
        base = self.start(allow_faults=False)
        st, out = self.post(base + "/api/fault", {"kind": "wipe"})
        self.assertEqual(st, 403)

    def test_REQ_LGT_001_light_modes_match_ssla_presets(self):
        self.assertEqual(MODES["phase-shift"][0], 6500)
        self.assertEqual(MODES["general"][0], 4500)
        self.assertEqual(MODES["pre-sleep"][0], 2700)
        cool, warm = mix(4500, 1.0)
        self.assertAlmostEqual(cool + warm, 1.0, places=3)
        self.assertGreater(cool, warm)

    def test_REQ_LGT_003_lights_are_adjustable_and_report_state(self):
        base = self.start()
        st, out = self.post(base + "/api/lights", {"mode": "red"})
        self.assertEqual((st, out["mode"], out["duty"]["cool"], out["duty"]["warm"]), (200, "red", 0.0, 0.0))
        st, _ = self.post(base + "/api/lights", {"mode": "disco"})
        self.assertEqual(st, 400)


class StaticChecks(unittest.TestCase):
    def test_REQ_OPS_001_no_outbound_network_code(self):
        pat = re.compile(r"urllib\.request|http\.client|^\s*(import|from) requests\b|socket\.(create_connection|connect)|\bfetch\(|XMLHttpRequest", re.M)
        offenders = []
        for base in ("service", "engine"):
            for dp, _, files in os.walk(os.path.join(ROOT, base)):
                for f in files:
                    if f.endswith((".py", ".js")):
                        with open(os.path.join(dp, f), encoding="utf-8") as fh:
                            txt = fh.read()
                        if pat.search(txt):
                            offenders.append(os.path.join(dp, f))
        self.assertEqual(offenders, [], "only the UI may call the local service; nothing calls out")

    def test_REQ_OPS_001_ui_calls_only_same_origin_paths(self):
        with open(os.path.join(ROOT, "web", "src", "store-remote.js"), encoding="utf-8") as fh:
            src = fh.read()
        for m in re.findall(r"call\('(?:GET|POST)', '([^']+)'", src):
            self.assertTrue(m.startswith("/api/"), m)
        self.assertNotIn("http://", src)
        self.assertNotIn("https://", src)


if __name__ == "__main__":
    unittest.main()
