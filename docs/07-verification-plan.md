# Verification plan

## Automated tests

| Suite | Command | Covers |
| --- | --- | --- |
| Engine | `node --test tests/js/*.test.js` | Model, planner, lighting rules, determinism |
| Data service | `python3 -m unittest discover -s tests/py` | Event log, recovery, API, lights, static network checks, cross-language checksums |
| Traceability | `python3 tools/trace.py` | Runs both suites and regenerates traceability.md |

## Fault-injection matrix

| ID | Fault | How it is injected | Pass criteria | Automated |
| --- | --- | --- | --- | --- |
| F-01 | Process killed mid-write | `tools/powercut_harness.py` (SIGKILL at random times) | No acknowledged record lost; at most the in-flight record kept; copies identical | Yes (30 cycles in tests; run 10,000 for FDR) |
| F-01R | True power loss | Pico cuts Pi power through a MOSFET at random times (`deploy/pico/`) | Same as F-01, checked by the Pi at each boot | Rig |
| F-02 | Corrupt active snapshot | `/api/fault corrupt-snapshot` or Systems tab | Boots from the other slot | Yes |
| F-03 | Bit flip in one copy | `/api/fault corrupt` | Vote repairs it; state unchanged | Yes |
| F-03b | Bit flips in two copies | Same record in two copies | Recovered from the remaining copy | Yes |
| F-04 | Record lost in all copies | Same record in all three | Degraded mode; loss reported | Yes |
| F-05 | RAM upset | Systems tab | Scrubber repairs within 3 s; fault logged | Demonstration |
| F-08 | Clock reset | Remove RTC battery or set clock back | Event order unaffected; operator asked to confirm time | Not built |
| F-09 | Delayed controller link | Two devices, network delay emulation | Packages apply once, in order | Not built |
| F-11 | Total wipe | `/api/fault wipe` | Safe Mode with guidance | Yes |

## Demonstrations for FDR

1. Boot the battery-powered Pi; show automatic start into Crew Mode (REQ-OPS-003).
2. Link lights; scrub the mission clock through a wind-down and a light window; LED panel follows and the light log records each change (REQ-LGT-003, -004, REQ-SAF-002).
3. Simulate a slam in Controller Mode, review the reasoning, approve, show the crew screen update (REQ-SAF-001, -002).
4. Run F-01R live: cut power several times; show the boot log after each.
5. Show the traceability matrix and open items.

## Measurements still needed

| Item | Instrument | Requirement |
| --- | --- | --- |
| Display luminance in each crew mode | Lux meter or phone light meter app, at a fixed distance | REQ-UI-004 |
| Light at the eye per mode | TSL2591 and a separate lux meter | REQ-LGT-004 |
| Plan time on the Pi | Validation tab | REQ-PLN-002 |
| Touch target size on the 7 in display | Ruler against the HIDH value | REQ-UI-003 |
