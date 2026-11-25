# Model credibility (NASA-STD-7009 self-assessment)

## Intended use

Predict a crew member's circadian phase and relative alertness over the next 14 days, and compare candidate sleep, light and nap schedules for a planned schedule change. Output is advisory input to a flight surgeon.

**Not intended for:** medical diagnosis, absolute performance prediction, fitness-for-duty decisions, or any use without human review.

## Model summary

| Part | Form | Source |
| --- | --- | --- |
| Light input (Process L) | Photoreceptor activation driving the pacemaker | Forger, Jewett & Kronauer (1999) |
| Pacemaker (Process C) | Modified van der Pol oscillator, intrinsic period τ per crew member | Forger, Jewett & Kronauer (1999) |
| Sleep pressure (Process S) | Exponential rise awake (τ 18.2 h) and decay asleep (τ 4.2 h) | Borbély two-process model |
| Sleep debt | Nightly shortfall against need, decaying over ~4 days | Prototype assumption |
| Sleep inertia | Penalty on waking scaled by expected deep-sleep fraction, 18 min decay | Prototype assumption |
| Readiness | Weighted sum of the above, 0–100 | **Placeholder weights** |

Integration: fixed-step RK4, 6 min step, deterministic (REQ-VER-001).

## Credibility factors

| Factor | Current level | Evidence | Gap |
| --- | --- | --- | --- |
| Verification | Good | Entrainment test; determinism test; cross-language checks | — |
| Validation | Weak | PRC has correct shape (REQ-MDL-002) | Crossover misses ±1 h target (OI-1); no comparison with published PRC data points yet |
| Input pedigree | Moderate | Published constants | Light inputs are assumed until the sensor rig runs |
| Uncertainty | Weak | Monte Carlo over τ 23.7–24.7 h | Readiness weights unfitted (OI-2) |
| Robustness | Moderate | Plans tested across slam sizes and timing | No sensitivity analysis of constants |
| Use history | None | New | — |
| M&S management | Moderate | Version control; tests in repo | No formal review records |
| People qualifications | Student team | — | Mentor review recommended |

## Open items

| ID | Item | Plan to close |
| --- | --- | --- |
| OI-1 | PRC crossover is about −1.5 h, target ±1 h (REQ-MDL-003) | Replicate the published human PRC protocol in simulation, compare point by point, and adjust the CBTmin offset only if the published constants are correctly transcribed. |
| OI-2 | Readiness weights are placeholders (REQ-MDL-004) | 1–2 week volunteer study with sleep tracker and daily 3-minute PVT (NASA PVT+ or a built-in PVT); fit weights; report fit error. Get school or advisor approval and consent first. |
| OI-3 | Per-person τ estimation not built (REQ-MDL-005) | Add a filter that updates τ and phase from logged sleep and light data; test on synthetic crew with known τ. |
| OI-4 | Light inputs are simulated | Run the TSL2591 sensor on the rig and feed measured lux into the model. |
