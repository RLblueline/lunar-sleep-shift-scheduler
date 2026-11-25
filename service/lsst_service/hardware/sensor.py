"""Light sensing. Requirement: REQ-LGT-004.

TSL2591 gives photopic lux only. It cannot estimate melanopic (circadian)
light, so readings are logged as photopic lux and the engine treats them as an
upper bound. An AS7341 spectral sensor is the planned upgrade for melanopic EDI.
"""
from __future__ import annotations

import time

# Approximate lux at the eye for each simulated mode (prototype assumption).
SIM_LUX = {"phase-shift": 1500, "general": 250, "pre-sleep": 60, "red": 5, "off": 0}


class SimulatedSensor:
    kind = "simulated"

    def __init__(self, lights):
        self.lights = lights

    def read(self) -> dict:
        return {"sensor": self.kind, "lux": SIM_LUX.get(self.lights.mode, 0), "at": int(time.time() * 1000)}


class TSL2591:
    """Minimal TSL2591 driver over I2C (smbus2). Address 0x29, gain 25x, 300 ms integration."""

    kind = "tsl2591"
    ADDR, CMD = 0x29, 0xA0
    ENABLE, CONTROL, C0DATAL = 0x00, 0x01, 0x14
    GAIN_MED, ATIME_300 = 0x10, 0x02
    AGAIN, ATIME_MS, LUX_DF = 25.0, 300.0, 408.0

    def __init__(self, bus: int = 1):
        from smbus2 import SMBus  # imported only on the Pi
        self.bus = SMBus(bus)
        self.bus.write_byte_data(self.ADDR, self.CMD | self.ENABLE, 0x03)  # power on + ALS
        self.bus.write_byte_data(self.ADDR, self.CMD | self.CONTROL, self.GAIN_MED | self.ATIME_300)
        time.sleep(0.35)

    def read(self) -> dict:
        d = self.bus.read_i2c_block_data(self.ADDR, self.CMD | self.C0DATAL, 4)
        ch0, ch1 = d[0] | d[1] << 8, d[2] | d[3] << 8
        if ch0 == 0 or ch0 >= 0xFFFF:
            lux = 0.0 if ch0 == 0 else float("inf")
        else:
            cpl = (self.ATIME_MS * self.AGAIN) / self.LUX_DF
            lux = max(0.0, (ch0 - ch1) * (1 - ch1 / ch0) / cpl)
        return {"sensor": self.kind, "lux": round(lux, 1), "ch0": ch0, "ch1": ch1, "at": int(time.time() * 1000)}


def make_sensor(driver: str, lights):
    if driver == "tsl2591":
        return TSL2591()
    return SimulatedSensor(lights)
