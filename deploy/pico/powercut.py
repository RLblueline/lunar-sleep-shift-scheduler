# MicroPython for a Raspberry Pi Pico: true power-loss test rig (verification F-01R, REQ-DAT-002).
#
# Wiring: GP15 -> gate of a logic-level N-MOSFET (or relay module) that switches the Pi's
# 5 V supply from the battery HAT. The Pico must be powered separately so it keeps running.
# The Pi records its own boot status in the event log on every start; afterwards run
#   python3 tools/boot_report.py
# on the Pi to count Nominal / Degraded / Safe Mode boots.
#
# Each cycle: power on, let the Pi boot and write for a random time, then cut power.
import machine
import random
import time

POWER = machine.Pin(15, machine.Pin.OUT, value=1)
LED = machine.Pin("LED", machine.Pin.OUT)
BOOT_S = 60          # seconds for the Pi to boot and open the UI
RUN_MIN, RUN_MAX = 5, 90   # seconds of normal running before the cut
OFF_S = 5            # seconds without power
CYCLES = 500

for n in range(1, CYCLES + 1):
    POWER.value(1)
    LED.value(1)
    time.sleep(BOOT_S + random.randint(RUN_MIN, RUN_MAX))
    POWER.value(0)          # cut power with no warning
    LED.value(0)
    print("cycle", n, "power cut at", time.ticks_ms())
    time.sleep(OFF_S)

POWER.value(1)
print("done:", CYCLES, "cycles")
