# Software hazard analysis

Scope: what can go wrong for the crew if the tool behaves incorrectly. Severity and likelihood are qualitative (prototype level). Consequences are fatigue-related; none is immediate injury.

| ID | Hazard | Possible causes | Effect on crew | Controls | Verified by |
| --- | --- | --- | --- | --- | --- |
| H-1 | Plan recommends light at the wrong circadian time, shifting the clock the wrong way | Model error; wrong phase estimate; wrong intrinsic period | Worse misalignment, lower alertness during critical task | Model validation (REQ-MDL-002/003); every plan explains itself and flags gaps (REQ-SAF-001); surgeon approval (REQ-SAF-002) | Tests, demonstration |
| H-2 | Unreviewed schedule reaches crew | Software bug; operator error | Crew follows a bad plan | Two-step approval; drafts never sent until approved; timeline versions logged | Demonstration |
| H-3 | Sleep cut too short | Planner bug; critical block overlapping sleep | Sleep debt | Minimum 6.5 h main sleep (REQ-PLN-001); recovery sleep after split nights | Test |
| H-4 | Stored data corrupted silently | Bit flip; power loss mid-write | Plans built on wrong history | Checksums and hash chain (REQ-DAT-001); three copies with voting (REQ-DAT-003); loss reported, never hidden (REQ-DAT-004) | Tests, kill harness |
| H-5 | Tool unavailable after a fault | Corrupt state at boot | No guidance during a slam shift | Automatic recovery (REQ-OPS-003); Safe Mode with generic guidance (REQ-DAT-007) | Tests, demonstration |
| H-6 | Display or lights emit blue light at night | UI bug; lights left in wrong mode | Melatonin suppression, worse sleep | Red-only display modes (REQ-UI-001); lights follow plan only when linked (REQ-SAF-002); light log (REQ-LGT-004) | Inspection, demonstration |
| H-7 | Alert prompts confused with vehicle alarms | Prompt design | Distraction, alarm fatigue | Advisory tier only, no alarm colours or tones, prompt limits, suppressed in critical blocks (REQ-UI-002) | Demonstration |
| H-8 | Test tools used in operations | Fault injection left enabled | Deliberate data damage | Disabled by configuration (REQ-SAF-003) | Test |

## Residual risk

The largest remaining risk is H-1: the readiness weights are not yet fitted to human data (open item OI-2), and the PRC crossover misses its target (OI-1). Until both close, plans must be presented as model predictions for review, not as validated guidance.
