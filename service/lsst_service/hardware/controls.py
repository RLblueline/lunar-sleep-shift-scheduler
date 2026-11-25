"""Front-panel and edge controls. Requirements: REQ-HW-011, REQ-HW-012, REQ-HW-014, REQ-HW-016.

Front panel (glove-sized, see docs/08-hardware-design.md):
    ACK     momentary key, confirms the current crew prompt          BCM 17
    SNOOZE  momentary key, snoozes the current prompt 15 min         BCM 5
    LIGHTS  latching toggle under a flip-up cover: up LINK, down MAN BCM 27
    MODE    latching toggle under a flip-up cover: up CREW, down CTRL BCM 6 (CTRL throw grounded)
Edge, recessed in wells:
    TEST    latching toggle; fault injection works only when it is on BCM 22
    EXT_PWR charger-present sense from the charge board              BCM 24
Output:
    LED     red ACK backlight, PWM, never above 30 % duty            BCM 23

Keys are counted, not polled for level: the UI reads the press counters and acts once per
new press, so a slow UI poll can never miss or double a press. Every input is wired to
ground with the Pi's internal pull-up. Each switch grounds the throw whose loss is harmless, so a
broken wire reads LIGHTS = MAN, MODE = CREW, TEST = off, charger = absent.
"""
from __future__ import annotations

import math
import threading
import time

KEYS = ("ACK", "SNOOZE")
PINS = {"ACK": 17, "SNOOZE": 5, "LIGHTS": 27, "MODE": 6, "TEST": 22, "EXT_PWR": 24, "LED": 23}
INDICATOR_MAX = 0.30   # REQ-HW-014: the only indicator stays dim and red

# pattern -> function of time (s) giving duty 0..1 before the cap is applied
PATTERNS = {
    "off": lambda t: 0.0,
    "steady": lambda t: 0.10,
    "night": lambda t: 0.04,                                         # sleep / wind-down: barely visible
    "prompt": lambda t: 0.15 * (1 - math.cos(2 * math.pi * t / 4)),  # slow 4 s breathe, peak 0.30
}


def capped(duty: float) -> float:
    return round(max(0.0, min(INDICATOR_MAX, duty)), 4)


class SimulatedControls:
    """Laptop stand-in. The Systems screen drives it through POST /api/sim."""

    kind = "simulated"

    def __init__(self):
        self._lock = threading.Lock()
        self.presses = {k: 0 for k in KEYS}
        self.lights_link = False
        self.mode = "crew"
        self.test_mode = False
        self.ext_power = True
        self.pattern = "off"

    # inputs
    def press(self, key: str) -> None:
        if key not in KEYS:
            raise ValueError(f"unknown key {key!r}")
        with self._lock:
            self.presses[key] += 1

    def set_inputs(self, **kw) -> None:
        with self._lock:
            for k in ("lights_link", "test_mode", "ext_power"):
                if k in kw and kw[k] is not None:
                    setattr(self, k, bool(kw[k]))
            if kw.get("mode") is not None:
                if kw["mode"] not in ("crew", "ctrl"):
                    raise ValueError("mode must be 'crew' or 'ctrl'")
                self.mode = kw["mode"]

    # output
    def set_indicator(self, pattern: str) -> str:
        if pattern not in PATTERNS:
            raise ValueError(f"unknown indicator pattern {pattern!r}")
        self.pattern = pattern
        return pattern

    def indicator_duty(self, t: float | None = None) -> float:
        return capped(PATTERNS[self.pattern](time.monotonic() if t is None else t))

    def state(self) -> dict:
        with self._lock:
            return {"driver": self.kind, "presses": dict(self.presses), "lights_link": self.lights_link,
                    "mode": self.mode, "test_mode": self.test_mode, "ext_power": self.ext_power,
                    "indicator": self.pattern}


class GpioControls(SimulatedControls):
    """Raspberry Pi driver (gpiozero). Imported only on the Pi."""

    kind = "gpio"

    def __init__(self, pins: dict | None = None):
        from gpiozero import Button, PWMLED
        super().__init__()
        p = {**PINS, **(pins or {})}
        self._keys = {k: Button(p[k], pull_up=True, bounce_time=0.03) for k in KEYS}
        for k, b in self._keys.items():
            b.when_pressed = (lambda key=k: SimulatedControls.press(self, key))
        self._toggles = {n: Button(p[n], pull_up=True, bounce_time=0.05) for n in ("LIGHTS", "MODE", "TEST", "EXT_PWR")}
        self._led = PWMLED(p["LED"], frequency=500)
        self._stop = threading.Event()
        threading.Thread(target=self._led_loop, name="ack-led", daemon=True).start()

    def _led_loop(self):
        while not self._stop.wait(0.05):
            self._led.value = self.indicator_duty()

    def state(self) -> dict:
        # switch closed to ground = up position
        self.lights_link = self._toggles["LIGHTS"].is_pressed
        self.mode = "ctrl" if self._toggles["MODE"].is_pressed else "crew"   # open wire -> crew screen
        self.test_mode = self._toggles["TEST"].is_pressed
        self.ext_power = self._toggles["EXT_PWR"].is_pressed
        return super().state()

    def set_inputs(self, **kw):
        raise PermissionError("Hardware switches cannot be set from software.")


def make_controls(driver: str):
    return GpioControls() if driver == "gpio" else SimulatedControls()
