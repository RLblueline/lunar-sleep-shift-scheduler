# Software requirements

Each requirement has one ID used everywhere: in tests (the test name starts with the ID), in the tailoring matrix and in the traceability report. Verification methods follow the NASA convention: **T** test, **A** analysis, **D** demonstration, **I** inspection.

Status is never edited here. Run `python3 tools/trace.py` to regenerate [traceability.md](traceability.md).

## Operations

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-OPS-001 | The system shall run with no network connection and make no outbound network calls. | Project constraint (deep-space edge computing) | T/I | Lunar habitat may have no link to Earth for hours. |
| REQ-OPS-002 | The data service shall accept connections from the local device only. | NASA-STD-8739.8 (software security) | T | Nothing outside the device can change crew data. |
| REQ-OPS-003 | The system shall start without operator input after power is restored. | Project constraint | D | Crew must not have to repair the tool after a fault. |

## Physiology model

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-MDL-001 | The circadian model shall entrain stably to a 24 h light/dark schedule (predicted CBTmin varies by less than 0.25 h day to day). | NASA-STD-7009 (verification) | T | Basic check that the oscillator is coded correctly. |
| REQ-MDL-002 | The model's phase response to light shall show both a delay region and an advance region. | NASA-STD-7009 (validation) | T | The planner depends on light timing pushing the clock the right way. |
| REQ-MDL-003 | The delay-to-advance crossover of the model PRC shall lie within ±1 h of predicted CBTmin. | NASA-STD-7009 (validation) | T | Published human PRCs cross near CBTmin. |
| REQ-MDL-004 | Readiness weights shall be fitted to measured PVT data, with fit error reported. | NASA-STD-7009 (validation, uncertainty) | A | Current weights are placeholders. |
| REQ-MDL-005 | Each crew profile shall carry its own intrinsic period and update it from logged sleep and light data. | Blueprint §1.1 | A/T | Body clocks differ by about ±0.2 h. |

## Planning

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-PLN-001 | Every main sleep opportunity in a generated plan shall be at least 6.5 h. | NASA-STD-3001 (sleep requirement ID to be confirmed); blueprint §1.3 | T | Protects sleep while shifting. |
| REQ-PLN-002 | A 14-day plan for one crew member shall be generated in under 2 s on target hardware. | Blueprint (bounded compute) | T | Controllers iterate on what-if drafts. |
| REQ-PLN-003 | The planner shall never schedule sleep or naps inside a critical block. | Blueprint §1.3 | T | Ops constraints are hard limits. |
| REQ-PLN-004 | For the reference slam scenario, the plan shall raise worst predicted readiness during the critical block above the unmitigated case. | Blueprint §1.3 | T | The tool must do better than doing nothing. |
| REQ-PLN-005 | When fewer than 2 nights are available before the critical block, the planner shall hold the clock and mitigate instead of shifting. | Blueprint §1.3 step 2 | T | Partial shifts cost more than holding. |

## Lighting

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-LGT-001 | Light modes shall match the ISS SSLA presets: phase-shift 6500 K, general 4500 K, pre-sleep 2700 K. | NASA-STD-3001 V2 8055; Maida 2014 | T | Uses lighting habitats already have. |
| REQ-LGT-002 | Every main sleep shall be preceded by a 2 h red or pre-sleep light window. | OCHMO-TB-026 (red light before sleep) | T | Protects melatonin onset. |
| REQ-LGT-003 | Lighting shall be adjustable by the crew and report its current state. | NASA-STD-3001 V2 8057 | T | Crew keep control of their environment. |
| REQ-LGT-004 | Measured light shall be logged with every light change. | Blueprint §2.1 (light log) | D | Model inputs must be traceable to measurements. |
| REQ-LGT-005 | Alerting light shall never be scheduled during sleep or naps. | OCHMO-TB-026 | T | Light during sleep disrupts it. |

## Data and fault tolerance

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-DAT-001 | Every record shall carry a checksum and the checksum of the previous record. | Blueprint §2.2; NASA-STD-8739.8 | T | Detects bit flips, gaps and reordering. |
| REQ-DAT-002 | A write shall be acknowledged only after it is on non-volatile storage in every copy; no acknowledged record shall be lost to a crash. | Blueprint §2.2 | T | The screen never shows data that can vanish. |
| REQ-DAT-003 | The log shall be kept in three copies and repaired by majority vote at boot. | Blueprint §2.2 (SEU tolerance) | T | Survives a bit flip in up to two copies of a record. |
| REQ-DAT-004 | A record lost in every copy shall be reported, and the system shall continue in Degraded mode. | Blueprint §2.3 | T | Never hide data loss. |
| REQ-DAT-005 | A partly written record shall be discarded at boot without affecting earlier records. | Blueprint §2.3 | T | Power cut mid-write. |
| REQ-DAT-006 | State snapshots shall use two slots so a damaged slot falls back to the other. | Blueprint §2.2 | T | A crash during a snapshot cannot lose state. |
| REQ-DAT-007 | After total data loss the system shall start in Safe Mode with generic guidance, never a blank screen. | Blueprint §2.3 | T/D | Crew always has something usable. |

## Crew interface

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-UI-001 | Outside alert windows, the crew display shall show no blue-channel content; wind-down and sleep modes shall be deep red on true black. | NASA-STD-3001 V2 8055; OCHMO-TB-026 | I | The screen must not undo the light plan. |
| REQ-UI-002 | Biological prompts shall be advisory-tier, limited per day, and never shown during sleep or critical blocks. | Blueprint §3.2 | D | Avoids alarm fatigue and confusion with vehicle alarms. |
| REQ-UI-003 | Touch targets shall meet the HIDH minimum size for gloved use. | HIDH (section to be confirmed) | I | Fatigued, possibly gloved users. |
| REQ-UI-004 | Display luminance in wind-down and sleep modes shall be measured and reported. | OCHMO-TB-026 | A | Claims about "dim" must be measured. |

## Safety

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-SAF-001 | Every plan shall state why it was chosen and flag any remaining readiness gap. | NASA-STD-8739.8 (hazard control H-1) | T | Humans can catch a wrong recommendation. |
| REQ-SAF-002 | Schedule changes shall reach crew devices only after explicit two-step approval; lights shall follow the plan only when an operator links them. | NASA-STD-8739.8 (hazard control H-2) | D | The tool advises; people decide. |
| REQ-SAF-003 | Fault injection shall be disabled by configuration outside test builds. | NASA-STD-8739.8 | T | Test tools must not be usable in operations. |

## Verification support

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-VER-001 | The engine shall be deterministic: identical inputs give bit-identical outputs. | NASA-STD-7009 (reproducibility) | T | Recovery by replay depends on it. |
| REQ-VER-002 | The system shall include fault injection for the cases in the verification plan. | Blueprint §4.1 | D | Faults must be testable on demand. |
| REQ-VER-003 | Records written by the service shall verify with the UI's checksum code. | Project | T | Two implementations of one format must agree. |

## Tablet hardware

Enclosure checks are computed from the CAD model by `cad/check.py` (results in [09-hardware-checks.md](09-hardware-checks.md)); the tests read that report and refuse a stale one.

| ID | Requirement | Source | Method | Rationale |
| --- | --- | --- | --- | --- |
| REQ-HW-001 | Exposed corners and edges shall be rounded: plan-view corners R ≥ 13 mm, edges R ≥ 3 mm (values to be confirmed against NASA-STD-3001 Tables 9.3-1/9.3-2). | NASA-STD-3001 V2 9009, 9011 | A | Prevents cuts and snags on a hand-held unit. |
| REQ-HW-002 | Toggles shall be guarded: MAIN and TEST recessed in wells, LIGHTS and MODE under hinged flip-up safety covers; the power key shall be recessed. | NASA-STD-3001 V2 10027 | A/I | A bump must not power off the tablet or enable fault tools. |
| REQ-HW-003 | Front pushbuttons shall be at least 19 mm across with at least 10 mm between them; front toggles at least 19 mm apart. | Gloved-use design target; confirm vs NASA-STD-3001 Table 10.4-4 (V2 10070) | A | Usable with gloves and when fatigued. |
| REQ-HW-004 | No part shall interfere with another; all fits shall be designed (no accidental contact). | Good practice | A | The CAD must assemble as drawn. |
| REQ-HW-005 | Every printed part shall be a single watertight solid that fits a 250 × 210 mm bed, has walls ≥ 0.8 mm locally (2.4 mm structural), and prints without support. | FDM design rules | A | Reproducible builds by any team member. |
| REQ-HW-006 | The tablet shall provide a means of grasping and a tether point, and a standard mount. | NASA-STD-3001 V2 9016 | I | Loose items must be restrainable in microgravity. |
| REQ-HW-007 | External connectors shall be keyed, differ in shape, and be spaced for gloved hands. | NASA-STD-3001 V2 9029, 9030, 9032 | A/I | Cables cannot be swapped or mismated. |
| REQ-HW-008 | The battery shall use protected cylindrical Li-ion cells with a BMS, fuse and disconnect; estimated mass ≤ 1000 g. | JSC 20793 (to be confirmed) | A/T | Battery safety; hand-held comfort. |
| REQ-HW-009 | Vent area shall be at least the cooler fan inlet area, with finger-safe slots (≤ 2.2 mm). | Pi 5 thermal design | A/T | Keeps the SoC below throttling. |
| REQ-HW-010 | Every control and connector shall be labelled; front labels at least 2.8 mm tall (0.4° at 400 mm). | NASA-STD-3001 V2 9118, 10066 | I | Crew can identify controls without the manual. |
| REQ-HW-011 | Pressing ACK shall confirm the current crew prompt; pressing SNOOZE shall snooze it for 15 minutes. | Blueprint §3.2 | T | Glove-friendly physical control of the two most frequent actions. |
| REQ-HW-012 | Fault injection shall be possible only when the build allows it and the guarded TEST switch is on. | NASA-STD-8739.8; REQ-SAF-003 | T | Test tools need a deliberate physical action. |
| REQ-HW-013 | On sustained low battery without a charger, the tablet shall log the event durably and then shut down cleanly, exactly once. | Blueprint §2.3 | T | No data loss and no brown-out corruption. |
| REQ-HW-014 | The only indicator, the ACK backlight, shall be a single red LED at ≤ 30 % duty. | OCHMO-TB-026; REQ-UI-001 | T/I | An indicator must not add blue light at night. |
| REQ-HW-015 | Display backlight shall follow the crew display state (alert, neutral, wind-down, sleep). | NASA-STD-3001 V2 8055; REQ-UI-004 | T | The screen must not undo the light plan. |
| REQ-HW-016 | The LIGHTS toggle (LINK/MAN) shall set the lights link and the MODE toggle (CREW/CTRL) the screen; each change is logged, and the switch position always wins. | Blueprint §3.1, §3.3 | T | A latching switch shows its state at a glance, even with the screen off. |
