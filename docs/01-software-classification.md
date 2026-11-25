# Software classification

**Proposed: NPR 7150.2D Class C, not safety-critical.** Confirm against the class definitions in NPR 7150.2D Appendix D with the project mentor before FDR.

## Why Class C

- The tool supports crew health decisions in a human spaceflight setting, which places it above research-only software (Classes D and E).
- It never commands vehicle systems. Lights change only when an operator links them, and every schedule change needs human approval (REQ-SAF-002).
- It is not Class A: it is not part of a system whose failure could directly cause loss of crew or vehicle.

## Why not safety-critical

A wrong recommendation could lead to poorer sleep or lower alertness. It cannot by itself cause a hazardous event, because:

1. Recommendations are advisory and labelled as such.
2. A flight surgeon approves every timeline before it reaches crew devices.
3. Every plan states its reasoning and flags readiness gaps (REQ-SAF-001).
4. On data loss the tool falls back to generic, conservative guidance (Safe Mode).

The hazard analysis in [04-hazard-analysis.md](04-hazard-analysis.md) records these controls. If a reviewer judges that crew might act on a recommendation without review, the classification should be revisited.

## What the classification commits us to

The Class C requirements we apply, tailor or waive are listed in [03-tailoring-matrix.md](03-tailoring-matrix.md). Practices in place now:

- written, numbered requirements with a verification method each ([02-requirements.md](02-requirements.md))
- version control for code and documents (git)
- automated tests tied to requirement IDs, with a generated traceability matrix ([traceability.md](traceability.md))
- documented architecture, hazards and model credibility
- peer review of changes before merge (team process; see the matrix)
