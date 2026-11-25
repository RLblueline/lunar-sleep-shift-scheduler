# Team plan

Four people, four roles, six two-week sprints to the Final Design Review. **Move the dates to match the HUNCH FDR deadline your mentor gives you**; the order of the work stays the same.

Once the issues are on GitHub, they are the source of truth. This page explains the plan; the board tracks it.

## Roles

Each role owns a part of the repo and its open items. Owners don't work alone: they make sure the work happens, get it reviewed, and ask for help early.

| Role | Owns | Open items | Folders |
| --- | --- | --- | --- |
| **Systems lead** | Requirements, NASA compliance, reviews, mentor contact, FDR package | HW-OI-2, DEV-1, DEV-2, REQ-UI-003 source | `docs/`, `tools/` |
| **Model & science lead** | Circadian model validation, readiness fitting, per-person clocks | OI-1, OI-2, OI-3 (REQ-MDL-003/004/005) | `engine/`, `tests/js/` |
| **Software & UI lead** | Crew and Controller screens, data service, Pi bring-up, durability tests | REQ-UI-003/004, F-08, HW-OI-6 | `web/`, `service/`, `deploy/` |
| **Hardware & CAD lead** | Parts, printing, wiring, battery, thermal, enclosure changes | HW-OI-1, -3, -4, -5, -7, OI-4 | `cad/`, `deploy/pico/` |

Pick roles at the first meeting. A sensible split: whoever knows the codebase best takes Systems, so they can review everyone's pull requests.

## Sprints

| Sprint | Dates | Goal |
| --- | --- | --- |
| 1 | Nov 30 – Dec 13 | Everyone runs the app; parts ordered; NASA tables read; PRC work started |
| 2 | Dec 14 – Dec 27 | Test prints; real Pi boots to the crew screen; PVT study approved |
| 3 | Dec 28 – Jan 10 | First assembled tablet; durability runs on the Pi; covers fixed |
| 4 | Jan 11 – Jan 24 | Measurements: luminance, mass, heat, runtime; PVT data collected |
| 5 | Jan 25 – Feb 7 | Open items closed or written up; battery review; FDR package drafted |
| 6 | Feb 8 – Feb 21 | FDR dry run with the mentor; fix what the dry run finds |

## Backlog

Every row becomes a GitHub issue with a "done when" checklist (`tools/create_issues.py`). IDs match the issue titles.

| ID | Sprint | Role | Task | Refs |
| --- | --- | --- | --- | --- |
| T01 | 1 | Systems | Set up the GitHub workflow: branch protection, labels, project board | CONTRIBUTING.md |
| T02 | 1 | Systems | Read NASA-STD-3001 Tables 9.3-1, 9.3-2, 10.4-4 and App. F F.5-1; confirm our values | HW-OI-2, REQ-HW-001, REQ-HW-003 |
| T03 | 2 | Systems | Get mentor sign-off on deviations DEV-1 and DEV-2 | 03-tailoring-matrix.md |
| T04 | 2 | Systems | Confirm the HIDH sections for touch targets, sleep and lighting | REQ-UI-003, references.md |
| T05 | 5 | Systems | Build the FDR package and demo script | 07-verification-plan.md |
| T06 | 1 | Systems | Start a review rota so nobody approves their own work | 03-tailoring-matrix.md (peer review, software assurance) |
| T07 | 1 | Model | Fix the PRC crossover (OI-1) | REQ-MDL-003, 05-model-credibility.md |
| T08 | 2 | Model | Design and run the PVT study to fit readiness weights (OI-2) | REQ-MDL-004 |
| T09 | 3 | Model | Estimate each crew member's body-clock period (REQ-MDL-005) | OI-3 |
| T10 | 4 | Model | Sensitivity analysis of model constants | 05-model-credibility.md (robustness) |
| T11 | 2 | Software | Make the crew screen usable with gloves | REQ-UI-003 |
| T12 | 4 | Software | Measure display luminance in each crew mode | REQ-UI-004 |
| T13 | 2 | Software | Bring up the real Raspberry Pi 5 | REQ-OPS-003, deploy/pi/setup.sh |
| T14 | 3 | Software | Run the durability tests on the Pi: 10,000 kill-9 cycles and the Pico power-cut rig | F-01, F-01R, REQ-DAT-002 |
| T15 | 4 | Software | Handle a clock reset (fault F-08) | 07-verification-plan.md |
| T16 | 5 | Software | Add coulomb counting to the battery driver (HW-OI-6) | service/lsst_service/hardware/battery.py |
| T17 | 1 | Hardware | Order parts and measure the real modules | HW-OI-4, 08-hardware-design.md BOM |
| T18 | 2 | Hardware | Print test coupons, then the full set | REQ-HW-005 |
| T19 | 3 | Hardware | Wire and bench-test the power chain; decide on the charger | HW-OI-1, REQ-HW-013 |
| T20 | 3 | Hardware | Stop the switch covers drifting and test for pinching | HW-OI-7, NASA-STD-3001 V2 10077, 9013 |
| T21 | 4 | Hardware | Measure mass, temperature and runtime | HW-OI-5, REQ-HW-008, REQ-HW-009 |
| T22 | 5 | Hardware | Battery safety review pack (JSC 20793) | HW-OI-3, REQ-HW-008 |
| T23 | 4 | Hardware | Build the LED light panel and sensor rig | OI-4, REQ-LGT-004 |

## Critical path

Parts → test prints → assembled tablet → measurements → FDR. If parts slip, everything on the hardware side slips, so **order parts in week 1** (T17). The model work (T07–T10) and the software work (T11–T16) can run in parallel and don't need the tablet until Sprint 3.

## How we work

- **Weekly:** one 30-minute meeting. Each person says what they finished, what's next, and what's blocking them. Everything else happens in GitHub issues and pull requests.
- **Every change:** a branch, a pull request, one review from someone else, and green CI. See [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Reviews within 2 days.** A pull request waiting longer than that goes on the meeting agenda.
- **Review rota** (NPR 7150.2 wants the reviewer to be someone other than the author): Systems reviews Software, Software reviews Model, Model reviews Hardware, Hardware reviews Systems. Swap each sprint.
- **Definition of done:** the issue's checklist is ticked, tests pass, docs are updated in the same pull request, and `python3 tools/trace.py` still exits 0 or only lists known open items.

## Risks

| Risk | Effect | What we do |
| --- | --- | --- |
| Parts arrive late | No tablet for measurements | Order in week 1; software keeps working with simulated drivers |
| PVT study not approved in time | REQ-MDL-004 stays open at FDR | Start approval in Sprint 1; present the method and the placeholder honestly if needed |
| NASA table values differ from ours | Enclosure changes late | Read the tables in Sprint 1 (T02); the model is parametric, so changes are small |
| One person is the only one who understands a part | Work stops when they're busy | Reviews rotate, so at least two people have read every part |
