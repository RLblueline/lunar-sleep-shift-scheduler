"""Tablet hardware verification with simulated drivers. Test names carry requirement IDs (tools/trace.py)."""
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "service"))

from lsst_service.config import Config  # noqa: E402
from lsst_service.eventlog import read_text  # noqa: E402
from lsst_service.hardware.backlight import MIN_ON, SimulatedBacklight  # noqa: E402
from lsst_service.hardware.battery import soc_from_volts  # noqa: E402
from lsst_service.hardware.controls import INDICATOR_MAX, PATTERNS, SimulatedControls  # noqa: E402
from lsst_service.server import Service, make_handler  # noqa: E402


class Rig(unittest.TestCase):
    """A service with simulated hardware, plus helpers to call its API."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lsst-hw-")
        cfg = Config(port=0, web_root=os.path.join(ROOT, "web", "dist"), low_batt_hold_s=30)
        cfg.log_copies = [os.path.join(self.tmp, f"log.{c}") for c in "ABC"]
        cfg.state_dir = os.path.join(self.tmp, "state")
        self.svc = Service(cfg)
        self.shutdowns = []
        self.svc.shutdown_hook = lambda: self.shutdowns.append(1)
        httpd = HTTPServer(("127.0.0.1", 0), make_handler(self.svc))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def records(self, rtype):
        return [json.loads(l)[2] for l in read_text(self.svc.cfg.log_copies[0]).splitlines() if json.loads(l)[1] == rtype]


class ControlTests(Rig):
    def test_REQ_HW_011_each_key_press_is_counted_once(self):
        self.call("/api/sim", {"press": "ACK"})
        self.call("/api/sim", {"press": "ACK"})
        st, c = self.call("/api/sim", {"press": "SNOOZE"})
        self.assertEqual(st, 200)
        self.assertEqual(c["presses"], {"ACK": 2, "SNOOZE": 1})

    def test_REQ_HW_011_ui_acts_on_ack_and_snooze_presses(self):
        src = open(os.path.join(ROOT, "web", "src", "app.js"), encoding="utf-8").read()
        self.assertIn("function hardwareAck", src)
        self.assertIn("function hardwareSnooze", src)
        self.assertRegex(src, r"until: App\.t \+ 0\.25", "SNOOZE must defer the prompt by 15 minutes")

    def test_REQ_HW_012_faults_need_the_build_flag_and_the_test_switch(self):
        st, _ = self.call("/api/fault", {"kind": "wipe"})
        self.assertEqual(st, 403, "TEST switch off: refused")
        self.call("/api/sim", {"test_mode": True})
        st, out = self.call("/api/controls")
        self.assertTrue(out["faults_allowed"])
        st, _ = self.call("/api/fault", {"kind": "wipe"})
        self.assertEqual(st, 200)
        self.svc.cfg.allow_faults = False
        st, _ = self.call("/api/fault", {"kind": "wipe"})
        self.assertEqual(st, 403, "build flag off: refused even with TEST on")

    def test_REQ_HW_014_indicator_never_exceeds_30_percent_duty(self):
        c = SimulatedControls()
        for name in PATTERNS:
            c.set_indicator(name)
            peak = max(c.indicator_duty(t / 10) for t in range(0, 200))
            self.assertLessEqual(peak, INDICATOR_MAX, name)
        st, _ = self.call("/api/indicator", {"pattern": "strobe"})
        self.assertEqual(st, 400, "unknown patterns are refused")

    def test_REQ_HW_014_only_one_red_indicator_is_driven(self):
        src = open(os.path.join(ROOT, "service", "lsst_service", "hardware", "controls.py"), encoding="utf-8").read()
        self.assertEqual(len(re.findall(r"PWMLED\(", src)), 1)

    def test_REQ_HW_015_backlight_follows_display_state(self):
        b = SimulatedBacklight()
        self.assertEqual(b.set(0), MIN_ON, "never fully dark while running")
        self.assertEqual(b.set(5), 1.0)
        st, out = self.call("/api/backlight", {"level": 0.2})
        self.assertEqual((st, out["backlight"]), (200, 0.2))
        src = open(os.path.join(ROOT, "web", "src", "app.js"), encoding="utf-8").read()
        m = re.search(r"BACKLIGHT = (\{[^}]+\})", src)
        self.assertIsNotNone(m, "app.js must define a backlight level per crew state")
        levels = json.loads(re.sub(r"(\w+):", r'"\1":', m[1]))
        self.assertTrue(levels["alert"] > levels["neutral"] > levels["wind"] > levels["sleep"] > 0)

    def test_REQ_HW_016_lights_and_mode_switches_are_logged_and_win(self):
        self.call("/api/sim", {"lights_link": True})
        self.call("/api/sim", {"mode": "ctrl"})
        self.assertEqual(self.records("lightlink"), [{"linked": True, "source": "switch"}])
        self.assertEqual(self.records("switch"), [{"name": "MODE", "pos": "ctrl"}])
        _, c = self.call("/api/controls")
        self.assertTrue(c["lights_link"])
        self.assertEqual(c["mode"], "ctrl")
        src = open(os.path.join(ROOT, "web", "src", "app.js"), encoding="utf-8").read()
        self.assertIn("App.lightsFollow = c.lights_link", src, "the UI takes the link state from the switch")


class PowerTests(Rig):
    def test_REQ_HW_013_low_battery_logs_then_shuts_down_exactly_once(self):
        self.svc.controls.set_inputs(ext_power=False)
        self.svc.monitor_tick(0)                       # baseline: charger-disconnected logged
        self.svc.battery.set_pct(4)
        self.svc.monitor_tick(100)
        self.svc.monitor_tick(120)
        self.assertEqual(self.shutdowns, [], "must stay low for the full hold time")
        self.svc.monitor_tick(130.5)
        self.svc.monitor_tick(140)
        self.assertEqual(self.shutdowns, [1], "exactly one shutdown")
        events = [r["event"] for r in self.records("power")]
        self.assertEqual(events.count("low-battery-shutdown"), 1)
        self.assertIn("charger-disconnected", events)

    def test_REQ_HW_013_charger_cancels_low_battery_shutdown(self):
        self.svc.controls.set_inputs(ext_power=False)
        self.svc.battery.set_pct(3)
        self.svc.monitor_tick(0)
        self.svc.controls.set_inputs(ext_power=True)
        self.svc.monitor_tick(40)
        self.svc.monitor_tick(80)
        self.assertEqual(self.shutdowns, [])

    def test_REQ_HW_013_state_of_charge_curve_is_monotonic(self):
        vals = [soc_from_volts(3.0 + i * 0.01) for i in range(0, 121)]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual((vals[0], vals[-1]), (0.0, 100.0))


if __name__ == "__main__":
    unittest.main()
