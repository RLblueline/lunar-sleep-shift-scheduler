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
 │  └───────────────────────────┘        └──────────────────────┘ │
 │                                                                 │
 └─────────────────────────────────────────────────────────────────┘
        ▲ power switched by MOSFET, driven by a separate Pico (power-cut test rig)
```

## Responsibilities

| Component | Owns | Does not do |
| --- | --- | --- |
| UI + engine (`engine/`, `web/src/`) | All planning and prediction; rebuilding state from the log; crew and controller screens | Write to disk directly; talk to hardware |
| Data service (`service/`) | Durable storage, recovery, snapshots, lights, sensor | Any planning logic |

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
| `POST /api/fault` | Fault injection (test builds only) |
| `GET/POST /api/state`, `/api/init`, `/api/alive` | Boot markers and uptime tracking |
