"""Configuration from environment variables. Defaults suit a laptop; deploy/pi/lsst.env suits the Pi."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _copies() -> list[str]:
    raw = os.environ.get("LSST_LOG_COPIES")
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    base = os.environ.get("LSST_DATA", os.path.join(ROOT, "data"))
    return [os.path.join(base, f"log.{c}") for c in "ABC"]


@dataclass
class Config:
    host: str = field(default_factory=lambda: os.environ.get("LSST_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("LSST_PORT", "8642")))
    log_copies: list = field(default_factory=_copies)
    state_dir: str = field(default_factory=lambda: os.environ.get("LSST_STATE", os.path.join(os.environ.get("LSST_DATA", os.path.join(ROOT, "data")), "state")))
    web_root: str = field(default_factory=lambda: os.environ.get("LSST_WEB", os.path.join(ROOT, "web", "dist")))
    lights_driver: str = field(default_factory=lambda: os.environ.get("LSST_LIGHTS", "sim"))
    sensor_driver: str = field(default_factory=lambda: os.environ.get("LSST_SENSOR", "sim"))
    controls_driver: str = field(default_factory=lambda: os.environ.get("LSST_CONTROLS", "sim"))
    battery_driver: str = field(default_factory=lambda: os.environ.get("LSST_BATTERY", "sim"))
    backlight_driver: str = field(default_factory=lambda: os.environ.get("LSST_BACKLIGHT", "sim"))
    shutdown_cmd: str = field(default_factory=lambda: os.environ.get("LSST_SHUTDOWN_CMD", ""))
    low_batt_pct: float = field(default_factory=lambda: float(os.environ.get("LSST_LOW_BATT_PCT", "5")))
    low_batt_hold_s: float = field(default_factory=lambda: float(os.environ.get("LSST_LOW_BATT_HOLD_S", "30")))
    allow_faults: bool = field(default_factory=lambda: os.environ.get("LSST_ALLOW_FAULTS", "1") == "1")
    verbose: bool = field(default_factory=lambda: os.environ.get("LSST_VERBOSE", "0") == "1")
