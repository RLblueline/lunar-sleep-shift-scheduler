# Architecture

Two processes on one Raspberry Pi, talking only over localhost.

```
 ┌──────────────── Raspberry Pi (battery powered) ────────────────┐
 │                                                                 │
 │  Chromium kiosk (touchscreen)          Python data service      │
 │  ┌───────────────────────────┐  HTTP   ┌──────────────────────┐ │
 │  │ Crew / Controller UI       │◀──────▶│ Event log (3 copies)  │─┼─▶ SD card: log.A, log.B
 │  │ Circadian engine (JS)      │ 127.0.0.1│ A/B snapshots         │─┼─▶ USB drive: log.C
 │  │ Slam-Shift planner         │  :8642 │ Light driver (PWM)    │─┼─▶ LED panel (cool/warm/red)
 │  │ Reducer: log → state       │        │ Sensor driver (I2C)   │◀┼── TSL2591 light sensor
 │  │ Hardware poll (400 ms)     │        │ Controls (GPIO)       │◀┼── ACK, SNOOZE, LIGHTS, MODE, TEST, charger
 │  │                            │        │ Battery (INA260, I2C) │◀┼── 1S2P 18650 pack
 │  │                            │        │ Backlight (sysfs)     │─┼─▶ Touch Display 2
 │  └───────────────────────────┘        │ Monitor thread (1 s)  │ │
 │                                        └──────────────────────┘ │
 │                                                                 │
 └─────────────────────────────────────────────────────────────────┘
        ▲ power switched by MOSFET, driven by a separate Pico (power-cut test rig)
```

## Responsibilities

| Component | Owns | Does not do |
| --- | --- | --- |
| UI + engine (`engine/`, `web/src/`) | All planning and prediction; rebuilding state from the log; crew and controller screens | Write to disk directly; talk to hardware |
| Data service (`service/`) | Durable storage, recovery, snapshots, lights, sensor, keys and switches, battery, backlight, low-battery shutdown | Any planning logic |

Keeping all model logic in one deterministic engine means the same code runs in the browser, in tests and on the Pi (REQ-VER-001).

## Data flow for one crew action

1. Crew taps **Skip** on a light prompt.
2. UI sends `POST /api/append {type:"rec", payload:{...}}` and waits.
3. Service writes the record to log.A, fsyncs; log.B, fsyncs; log.C, fsyncs; then replies.
4. UI checks the record's checksum with its own code, adds it to the log in memory, and rebuilds state.
5. Engine re-runs predictions without the skipped window; screen updates.

If power fails before step 3 finishes, the record was never acknowledged and the screen never showed it. At boot the service drops it (REQ-DAT-005).

## Boot sequence

1. systemd starts the data service; it runs recovery on all three copies.
2. Chromium kiosk opens the UI, which asks the service for the recovered log.
3. UI verifies every record's checksum, replays the log, compares with the newest valid snapshot, rebuilds plans and writes a new snapshot.
4. Status is Nominal, Degraded (data lost and reported) or Safe Mode (no usable data).

## Interfaces

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Version, log paths, drivers |
| `GET /api/recover` | Run recovery, return report and accepted records |
| `POST /api/append` | Durable append (returns after fsync of all copies) |
| `GET/POST /api/snapshot` | Read or write A/B snapshot |
| `GET/POST /api/lights` | Read state and sensor, or set mode |
| `POST /api/fault` | Fault injection (test builds only, TEST switch on) |
| `GET /api/controls` | Key press counters, switch positions, battery, charger, shutdown flag |
| `POST /api/indicator` | ACK light pattern: off, steady, night, prompt (capped at 30 % duty) |
| `POST /api/backlight` | Display backlight level 0.02 to 1 |
| `POST /api/sim` | Drive simulated keys, switches and battery (laptop only; refused with real hardware) |
| `GET/POST /api/state`, `/api/init`, `/api/alive` | Boot markers and uptime tracking |

## Hardware controls

The service owns every GPIO pin; the UI never touches hardware. The UI polls `GET /api/controls` every 400 ms.

- **Keys are counted, not sampled.** ACK and SNOOZE each have a press counter. The UI acts once per new count, so a slow poll can't miss or repeat a press.
- **Switches are the authority.** The LIGHTS toggle sets whether lights follow the plan; the MODE toggle picks the crew or controller screen. The service logs every change (`lightlink`, `switch` records), so the history survives a crash.
- **The UI drives the outputs.** On each render it asks for a backlight level by crew state (alert 100 %, neutral 60 %, wind-down 20 %, sleep 4 %) and an ACK light pattern.
- **Low battery.** A monitor thread checks the battery each second. At ≤ 5 % without a charger for 30 s it writes a `power` record (fsynced to all copies) and then runs the shutdown command once. The UI shows a "Battery empty" screen.
- **Fault tools need two keys.** `/api/fault` works only when the build allows faults and the recessed TEST switch is on.

On a laptop every driver is simulated, and the Systems screen shows buttons that stand in for the physical keys and switches.
