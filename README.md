# Lunar Sleep-Shift Scheduling Tool

Offline crew sleep, light and nap scheduler for lunar habitats (NASA HUNCH prototype). It predicts each crew member's body clock with a Kronauer-type circadian model, plans multi-day shifts for sudden schedule changes ("slam shifts"), drives habitat lighting, and stores every action in a crash-safe event log.

Designed to NASA standards with documented tailoring; not certified. See [docs/03-tailoring-matrix.md](docs/03-tailoring-matrix.md).

## Run it

**Laptop (no hardware):**
```sh
python3 web/build.py
cd service && python3 -m lsst_service      # then open http://127.0.0.1:8642
```
Opening `web/dist/index.html` directly also works, as a browser-only demo without durable storage.

**Raspberry Pi:** see [deploy/pi/setup.sh](deploy/pi/setup.sh). Read it before running; it changes boot behaviour.

No third-party Python packages are needed on a laptop. On the Pi, `gpiozero` and `smbus2` drive the LEDs and sensor.

## Check it

```sh
node --test tests/js/*.test.js                 # engine and planner
python3 -m unittest discover -s tests/py       # data service, recovery, API
python3 tools/trace.py                         # runs both, writes docs/traceability.md
python3 tools/powercut_harness.py --cycles 10000   # long kill-9 durability run
```

`tools/trace.py` exits non-zero while any test fails or a testable requirement has no test. Right now it reports one open item (REQ-MDL-003) and one unbuilt feature (REQ-MDL-005); both are listed in [docs/05-model-credibility.md](docs/05-model-credibility.md).

## Repository map

| Path | Contents |
| --- | --- |
| `engine/engine.js` | Circadian model, readiness, Slam-Shift planner (deterministic, shared by UI and tests) |
| `web/src/` | Crew, Controller, Systems and Validation screens; local and service-backed stores |
| `web/build.py` | Bundles everything into `web/dist/index.html` |
| `service/lsst_service/` | Python data service: event log, recovery, snapshots, HTTP API, light and sensor drivers |
| `tests/` | JS and Python tests; each test name starts with the requirement ID it verifies |
| `tools/` | Traceability report, kill-9 harness, boot report |
| `deploy/pi/` | Pi setup, systemd unit, kiosk launcher, configuration |
| `deploy/pico/` | Power-cut rig for true power-loss testing |
| `docs/` | Classification, requirements, tailoring matrix, hazards, model credibility, architecture, verification plan |

## Hardware (FDR unit)

| Part | Purpose |
| --- | --- |
| Raspberry Pi 4 or 5 + battery UPS HAT | Portable computer |
| Touchscreen (AMOLED preferred for true black) | Crew display |
| DS3231 real-time clock | Correct time with no network |
| TSL2591 light sensor (I2C) | Measured light for the light log |
| Cool-white, warm-white and red LED channels on logic-level MOSFETs (BCM 12, 13, 18) | SSLA-style habitat light modes |
| Industrial SD card + separate USB drive | Log copies on separate devices |
| Raspberry Pi Pico + MOSFET on the Pi's supply | Random power cuts for testing |
