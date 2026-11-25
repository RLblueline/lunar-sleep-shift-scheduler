"""Enclosure requirements, verified by analysis of the CAD model.

These tests read cad/out/check-report.json, written by `python3 cad/check.py`. They fail on a
report older than the model, so rerun the checker after any change to cad/tablet.py.
A check marked REVIEW waits on a NASA table value or a formal review: the test is skipped and
tools/trace.py lists the requirement as open.
"""
import hashlib
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT = os.path.join(ROOT, "cad", "out", "check-report.json")


def model_hash():
    h = hashlib.sha256()
    for f in ("tablet.py", "check.py"):
        with open(os.path.join(ROOT, "cad", f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:16]


class EnclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REPORT):
            raise unittest.SkipTest("No CAD report. Run: python3 cad/check.py (needs cadquery, trimesh)")
        with open(REPORT) as f:
            cls.rep = json.load(f)

    def verdict(self, req):
        self.assertEqual(self.rep["source_hash"], model_hash(), "CAD report is stale: run python3 cad/check.py")
        rows = [c for c in self.rep["checks"] if c["req"] == req]
        self.assertTrue(rows, f"no CAD check covers {req}")
        failed = [c["name"] for c in rows if c["status"] == "fail"]
        self.assertFalse(failed, f"{req} fails: {failed}")
        review = [c["name"] for c in rows if c["status"] == "review"]
        if review:
            self.skipTest("REVIEW: " + "; ".join(review))

    def test_REQ_HW_001_corners_and_edges_rounded(self): self.verdict("REQ-HW-001")
    def test_REQ_HW_002_toggles_and_power_key_guarded(self): self.verdict("REQ-HW-002")
    def test_REQ_HW_003_controls_sized_and_spaced_for_gloves(self): self.verdict("REQ-HW-003")
    def test_REQ_HW_004_parts_assemble_without_interference(self): self.verdict("REQ-HW-004")
    def test_REQ_HW_005_printed_parts_print_without_support(self): self.verdict("REQ-HW-005")
    def test_REQ_HW_007_connectors_keyed_and_spaced(self): self.verdict("REQ-HW-007")
    def test_REQ_HW_008_mass_and_battery(self): self.verdict("REQ-HW-008")
    def test_REQ_HW_009_vent_area(self): self.verdict("REQ-HW-009")
    def test_REQ_HW_010_labels(self): self.verdict("REQ-HW-010")


if __name__ == "__main__":
    unittest.main()
