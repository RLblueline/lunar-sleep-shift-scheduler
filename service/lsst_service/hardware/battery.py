"""Battery monitor. Requirement: REQ-HW-013.

Pack: two protected 18650 cells in parallel (1S2P, 3.6 V nominal, 25.2 Wh) through a BMS,
fuse and the MAIN switch, then a 5 V 5 A boost converter to the Pi.
Monitor: INA260 on I2C address 0x40, between the pack and the boost converter.
    bus voltage register 0x02, 1.25 mV per bit
    current register     0x01, 1.25 mA per bit (signed; positive = discharging)

State of charge is estimated from resting voltage with the curve below, so expect about
±10 % (open item HW-OI-6: add coulomb counting).
"""
from __future__ import annotations

# open-circuit voltage -> state of charge, typical protected Li-ion 18650 at room temperature
OCV_SOC = [(3.00, 0), (3.30, 5), (3.45, 10), (3.60, 20), (3.68, 30), (3.74, 40), (3.79, 50),
           (3.85, 60), (3.92, 70), (4.00, 80), (4.08, 90), (4.20, 100)]


def soc_from_volts(v: float) -> float:
    if v <= OCV_SOC[0][0]:
        return 0.0
    if v >= OCV_SOC[-1][0]:
        return 100.0
    for (v0, s0), (v1, s1) in zip(OCV_SOC, OCV_SOC[1:]):
        if v0 <= v <= v1:
            return round(s0 + (s1 - s0) * (v - v0) / (v1 - v0), 1)
    return 0.0


class SimulatedBattery:
    kind = "simulated"

    def __init__(self, pct: float = 80.0):
        self.pct = pct

    def set_pct(self, pct: float) -> None:
        self.pct = max(0.0, min(100.0, float(pct)))

    def read(self) -> dict:
        # invert the curve so the simulated voltage is consistent with the percentage
        v = OCV_SOC[0][0]
        for (v0, s0), (v1, s1) in zip(OCV_SOC, OCV_SOC[1:]):
            if s0 <= self.pct <= s1:
                v = v0 + (v1 - v0) * (self.pct - s0) / (s1 - s0)
                break
        else:
            v = OCV_SOC[-1][0]
        return {"driver": self.kind, "pct": round(self.pct, 1), "volts": round(v, 3), "amps": 1.10}


class Ina260Battery:
    kind = "ina260"

    def __init__(self, bus: int = 1, addr: int = 0x40):
        from smbus2 import SMBus
        self._bus, self._addr = SMBus(bus), addr

    def _reg(self, reg: int) -> int:
        raw = self._bus.read_word_data(self._addr, reg)
        return ((raw & 0xFF) << 8) | (raw >> 8)   # INA260 is big-endian

    def read(self) -> dict:
        volts = self._reg(0x02) * 0.00125
        cur = self._reg(0x01)
        if cur & 0x8000:
            cur -= 0x10000
        return {"driver": self.kind, "pct": soc_from_volts(volts), "volts": round(volts, 3), "amps": round(cur * 0.00125, 3)}


def make_battery(driver: str):
    return Ina260Battery() if driver == "ina260" else SimulatedBattery()
