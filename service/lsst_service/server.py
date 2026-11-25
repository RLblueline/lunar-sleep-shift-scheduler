"""Local data service: serves the crew/controller UI and owns all persistence and hardware.

Binds to 127.0.0.1 only (REQ-OPS-002). Requests are handled one at a time; a background
monitor thread (battery, charger, LIGHTS switch) shares one lock with them, so log writes
stay strictly ordered.
No outbound network calls anywhere in this package (REQ-OPS-001).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from .config import Config
from .eventlog import EventLog
from .hardware.lights import MODES, make_lights
from .hardware.sensor import make_sensor
from .hardware.controls import make_controls
from .hardware.battery import make_battery
from .hardware.backlight import make_backlight

VERSION = "0.3.0"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json"}


class Service:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.log = EventLog(cfg.log_copies, cfg.state_dir)
        self.lights = make_lights(cfg.lights_driver)
        self.sensor = make_sensor(cfg.sensor_driver, self.lights)
        self.controls = make_controls(cfg.controls_driver)
        self.battery = make_battery(cfg.battery_driver)
        self.backlight = make_backlight(cfg.backlight_driver)
        self.lock = threading.RLock()
        self.started = time.time()
        self.boot_report = self.log.recover().as_dict()
        self.low_since = None          # when the battery first read low without a charger
        self.shutting_down = False
        self.shutdown_hook = self._run_shutdown
        c = self.controls.state()
        self._last = {"ext_power": c["ext_power"], "lights_link": c["lights_link"], "mode": c["mode"]}

    # ---------- hardware monitor (REQ-HW-013, REQ-HW-016) ----------
    def faults_allowed(self) -> bool:
        """REQ-HW-012: the build must allow faults AND the guarded TEST switch must be on."""
        return self.cfg.allow_faults and self.controls.state()["test_mode"]

    def monitor_tick(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self.lock:
            c, b = self.controls.state(), self.battery.read()
            if c["ext_power"] != self._last["ext_power"]:
                self.log.append("power", {"event": "charger-connected" if c["ext_power"] else "charger-disconnected", "pct": b["pct"]})
            for key, rtype in (("lights_link", "lightlink"), ("mode", "switch")):
                if c[key] != self._last[key]:
                    payload = {"linked": c[key], "source": "switch"} if rtype == "lightlink" else {"name": "MODE", "pos": c[key]}
                    self.log.append(rtype, payload)
            self._last = {k: c[k] for k in self._last}
            low = b["pct"] <= self.cfg.low_batt_pct and not c["ext_power"]
            if not low:
                self.low_since = None
            elif self.low_since is None:
                self.low_since = now
            elif not self.shutting_down and now - self.low_since >= self.cfg.low_batt_hold_s:
                self.shutting_down = True   # set first: the shutdown happens exactly once
                self.log.append("power", {"event": "low-battery-shutdown", "pct": b["pct"], "volts": b["volts"]})
                self.shutdown_hook()

    def _run_shutdown(self) -> None:
        if self.cfg.shutdown_cmd:
            subprocess.Popen(shlex.split(self.cfg.shutdown_cmd))

    def start_monitor(self, period: float = 1.0) -> None:
        def loop():
            while True:
                try:
                    self.monitor_tick()
                except Exception as e:   # keep monitoring; a bad sensor read must not stop the service
                    print("monitor:", e, flush=True)
                time.sleep(period)
        threading.Thread(target=loop, name="hw-monitor", daemon=True).start()

    def controls_get(self, _):
        with self.lock:
            return 200, {**self.controls.state(), "battery": self.battery.read(), "backlight": self.backlight.level,
                         "shutting_down": self.shutting_down, "faults_allowed": self.faults_allowed()}

    def indicator_put(self, body):
        try:
            return 200, {"indicator": self.controls.set_indicator(str(body.get("pattern")))}
        except ValueError as e:
            return 400, {"error": str(e)}

    def backlight_put(self, body):
        try:
            return 200, {"backlight": self.backlight.set(float(body.get("level")))}
        except (TypeError, ValueError) as e:
            return 400, {"error": str(e)}

    def sim(self, body):
        """Drive simulated hardware from the Systems screen. Refused when real hardware is attached."""
        if self.controls.kind != "simulated":
            return 403, {"error": "Real controls are attached; use the switches."}
        try:
            if body.get("press"):
                self.controls.press(body["press"])
            self.controls.set_inputs(**{k: body.get(k) for k in ("lights_link", "test_mode", "ext_power", "mode")})
            if body.get("battery_pct") is not None and hasattr(self.battery, "set_pct"):
                self.battery.set_pct(body["battery_pct"])
        except ValueError as e:
            return 400, {"error": str(e)}
        c, b = self.controls.state(), self.battery.read()
        if self.shutting_down and (c["ext_power"] or b["pct"] > self.cfg.low_batt_pct):
            self.shutting_down = False   # simulated 'press PWR to restart'
            self.low_since = None
        self.monitor_tick()
        return self.controls_get(None)

    # each handler returns (status, body)
    def health(self, _):
        return 200, {"ok": True, "version": VERSION, "copies": self.log.paths, "faults": self.cfg.allow_faults, "controls": self.controls.kind, "battery": self.battery.kind, "backlight": self.backlight.kind,
                     "lights": self.lights.kind, "sensor": self.sensor.kind, "uptime_s": round(time.time() - self.started)}

    def state(self, _):
        return 200, {"init": self.log.is_init(), "alive": self.log.last_alive()}

    def init(self, _):
        self.log.mark_init(); return 200, {"init": True}

    def alive(self, _):
        self.log.alive(); return 200, {"alive": self.log.last_alive()}

    def recover(self, _):
        rep = self.log.recover().as_dict()
        return 200, {"report": rep, "lines": [r["line"] for r in self.log.records]}

    def append(self, body):
        rtype, payload = body.get("type"), body.get("payload")
        if not isinstance(rtype, str) or not rtype:
            return 400, {"error": "type is required"}
        rec = self.log.append(rtype, payload)   # returns only after every copy is fsynced
        return 200, {"line": rec["line"]}

    def snapshot_get(self, _):
        return 200, self.log.read_snapshot()

    def snapshot_put(self, body):
        return 200, {"slot": self.log.write_snapshot(int(body["seq"]), str(body["hash"]))}

    def linecount(self, _):
        return 200, {"counts": self.log.line_counts()}

    def fault(self, body):
        if not self.cfg.allow_faults:
            return 403, {"error": "Fault injection is disabled in this configuration."}
        if not self.controls.state()["test_mode"]:
            return 403, {"error": "Turn on the TEST switch to inject faults."}
        k = body.get("kind")
        if k == "corrupt":
            return 200, {"line": self.log.corrupt(int(body["copy"]), body.get("line"))}
        if k == "corrupt-snapshot":
            return 200, {"slot": self.log.corrupt_snapshot()}
        if k == "torn":
            return 200, {"seq": self.log.torn_append(body.get("type", "rec"), body.get("payload", {}))}
        if k == "wipe":
            self.log.wipe(); return 200, {"wiped": True}
        return 400, {"error": f"unknown fault {k!r}"}

    def lights_get(self, _):
        return 200, {**self.lights.state(), "reading": self.sensor.read(), "modes": list(MODES)}

    def lights_put(self, body):
        try:
            return 200, {**self.lights.set_mode(str(body.get("mode"))), "reading": self.sensor.read()}
        except ValueError as e:
            return 400, {"error": str(e)}


ROUTES = {
    ("GET", "/api/health"): "health", ("GET", "/api/state"): "state", ("POST", "/api/init"): "init",
    ("POST", "/api/alive"): "alive", ("GET", "/api/recover"): "recover", ("POST", "/api/append"): "append",
    ("GET", "/api/snapshot"): "snapshot_get", ("POST", "/api/snapshot"): "snapshot_put",
    ("GET", "/api/linecount"): "linecount", ("POST", "/api/fault"): "fault",
    ("GET", "/api/lights"): "lights_get", ("POST", "/api/lights"): "lights_put",
    ("GET", "/api/controls"): "controls_get", ("POST", "/api/indicator"): "indicator_put",
    ("POST", "/api/backlight"): "backlight_put", ("POST", "/api/sim"): "sim",
}


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LSST/" + VERSION

        def log_message(self, fmt, *args):
            if svc.cfg.verbose:
                super().log_message(fmt, *args)

        def _send(self, status, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method):
            path = urlparse(self.path).path
            name = ROUTES.get((method, path))
            if name:
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 1_000_000:
                        return self._send(413, {"error": "request too large"})
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError:
                        return self._send(400, {"error": "body is not valid JSON"})
                with svc.lock:
                    status, out = getattr(svc, name)(body)
                return self._send(status, out)
            if method == "GET":
                return self._static(path)
            return self._send(404, {"error": "not found"})

        def _static(self, path):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            full = os.path.realpath(os.path.join(svc.cfg.web_root, rel))
            if not full.startswith(os.path.realpath(svc.cfg.web_root) + os.sep) or not os.path.isfile(full):
                return self._send(404, {"error": "not found"})
            with open(full, "rb") as f:
                return self._send(200, f.read(), STATIC_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def serve(cfg: Config) -> None:
    svc = Service(cfg)
    svc.start_monitor()
    httpd = HTTPServer((cfg.host, cfg.port), make_handler(svc))
    print(f"LSST data service {VERSION} on http://{cfg.host}:{cfg.port}  "
          f"(records: {len(svc.log.records)}, repaired copies at start: {svc.boot_report['repaired']})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
