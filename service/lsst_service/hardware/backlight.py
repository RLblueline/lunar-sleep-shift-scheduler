"""Display backlight. Requirement: REQ-HW-015 (follow the crew display state).

The UI asks for a level per crew state (alert 1.0, neutral 0.6, wind-down 0.2, sleep 0.04).
On the Pi the Touch Display 2 backlight is a sysfs device; deploy/pi/99-lsst-backlight.rules
lets the service write it without root.
"""
from __future__ import annotations

import glob
import os

MIN_ON = 0.02   # never fully dark while running: a black screen looks like a crash


def clamp(level: float) -> float:
    return round(max(MIN_ON, min(1.0, float(level))), 3)


class SimulatedBacklight:
    kind = "simulated"

    def __init__(self):
        self.level = 1.0

    def set(self, level: float) -> float:
        self.level = clamp(level)
        return self.level


class SysfsBacklight(SimulatedBacklight):
    kind = "sysfs"

    def __init__(self, path: str | None = None):
        super().__init__()
        found = sorted(glob.glob("/sys/class/backlight/*"))
        if not (path or found):
            raise RuntimeError("no backlight device in /sys/class/backlight")
        self.path = path or found[0]
        with open(os.path.join(self.path, "max_brightness")) as f:
            self.max = int(f.read().strip())

    def set(self, level: float) -> float:
        self.level = clamp(level)
        with open(os.path.join(self.path, "brightness"), "w") as f:
            f.write(str(max(1, round(self.level * self.max))))
        return self.level


def make_backlight(driver: str):
    return SysfsBacklight() if driver == "sysfs" else SimulatedBacklight()
