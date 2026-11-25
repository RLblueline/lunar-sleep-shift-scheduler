"""Habitat light control. Requirements: REQ-LGT-001, REQ-LGT-003, REQ-SAF-002.

Modes mirror the ISS Solid State Lighting Assembly presets (Maida 2014):
    phase-shift  6500 K  blue-enriched, for clock shifting
    general      4500 K  normal daytime work
    pre-sleep    2700 K  evening, reduced blue
plus two prototype-specific modes:
    red          red channel only, melatonin-safe night light
    off          dark, sleep

Hardware: one cool-white (6500 K) LED channel, one warm-white (2700 K) channel
and one red channel, each driven by PWM through a logic-level MOSFET.
Intermediate colour temperatures are mixed in mired space.
"""
from __future__ import annotations

import threading

COOL_K, WARM_K = 6500, 2700

MODES = {
    # mode: (cct_kelvin or None, white brightness 0..1, red brightness 0..1)
    "phase-shift": (6500, 1.0, 0.0),
    "general": (4500, 0.6, 0.0),
    "pre-sleep": (2700, 0.25, 0.0),
    "red": (None, 0.0, 0.15),
    "off": (None, 0.0, 0.0),
}


def mix(cct: float | None, level: float) -> tuple[float, float]:
    """Return (cool, warm) duty cycles that reproduce cct at a total level."""
    if cct is None or level <= 0:
        return 0.0, 0.0
    m, mc, mw = 1e6 / cct, 1e6 / COOL_K, 1e6 / WARM_K
    f_cool = max(0.0, min(1.0, (m - mw) / (mc - mw)))
    return round(level * f_cool, 4), round(level * (1 - f_cool), 4)


class SimulatedLights:
    """Used on a laptop or when no LED hardware is attached."""

    kind = "simulated"

    def __init__(self):
        self.mode = "general"
        self.duty = self._duty("general")
        self._lock = threading.Lock()

    @staticmethod
    def _duty(mode: str) -> dict:
        cct, white, red = MODES[mode]
        cool, warm = mix(cct, white)
        return {"cool": cool, "warm": warm, "red": red}

    def set_mode(self, mode: str) -> dict:
        if mode not in MODES:
            raise ValueError(f"unknown light mode {mode!r}")
        with self._lock:
            self.mode = mode
            self.duty = self._duty(mode)
            self._apply(self.duty)
        return self.state()

    def _apply(self, duty: dict) -> None:
        pass

    def state(self) -> dict:
        cct = MODES[self.mode][0]
        return {"driver": self.kind, "mode": self.mode, "cct": cct, "duty": self.duty}


class PwmLights(SimulatedLights):
    """Raspberry Pi GPIO PWM driver (gpiozero). Pins are BCM numbers."""

    kind = "gpio-pwm"

    def __init__(self, cool_pin: int = 12, warm_pin: int = 13, red_pin: int = 18):
        from gpiozero import PWMLED  # imported only on the Pi
        self._leds = {"cool": PWMLED(cool_pin), "warm": PWMLED(warm_pin), "red": PWMLED(red_pin)}
        super().__init__()
        self._apply(self.duty)

    def _apply(self, duty: dict) -> None:
        for ch, led in self._leds.items():
            led.value = duty[ch]


def make_lights(driver: str):
    if driver == "gpio":
        return PwmLights()
    return SimulatedLights()
