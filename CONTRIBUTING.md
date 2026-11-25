# Contributing

How the four of us change this repo without breaking each other's work. New here? Read [docs/00-start-here.md](docs/00-start-here.md) first.

## The loop

0. **First week only:** the Systems lead protects `main`, runs `python3 tools/create_issues.py RLblueline/lunar-sleep-shift` (needs `gh auth login`) and builds the project board (T01). Until then, pick from [the team plan](docs/10-team-plan.md#backlog).
1. **Pick an issue** from the project board and assign yourself. No issue? Make one first, so the team knows what you're doing.
2. **Branch from main.** Name it `<issue number>-<short-name>`, for example `12-prc-crossover`.
   ```sh
   git switch main && git pull
   git switch -c 12-prc-crossover
   ```
3. **Make the change, with its test and its docs, in the same branch.**
4. **Run the checks** (below). They must pass before you ask for review.
5. **Open a pull request.** Write `Closes #12` in the description, fill in the template, and request a review from the person on the rota ([team plan](docs/10-team-plan.md#how-we-work)).
6. **Review within 2 days.** The reviewer runs the app, reads the diff, and either approves or leaves specific comments.
7. **Squash and merge** once it's approved and CI is green. Delete the branch.

Never push straight to `main`. Branch protection will stop you once it's set up (T01).

## Checks to run before a pull request

```sh
python3 web/build.py                          # if you touched web/ or engine/
node --test tests/js/*.test.js                # engine
python3 -m unittest discover -s tests/py      # service, hardware, enclosure report
python3 tools/trace.py                        # all of the above + traceability report; must exit 0
python3 cad/check.py                          # only if you touched cad/ (needs cadquery, trimesh)
```

CI runs the same commands on every pull request.

## Rules that keep the project NASA-traceable

- **Every change serves a requirement.** Find its ID in [02-requirements.md](docs/02-requirements.md). If none fits, add a requirement in the same pull request (ID, text, source, verification method, rationale).
- **Test names start with the requirement ID.** JavaScript: `test('REQ-PLN-003 never schedules sleep inside a critical block', ...)`. Python: `def test_REQ_HW_011_each_key_press_is_counted_once(self)`. That's how `tools/trace.py` links tests to requirements.
- **An open item is a TODO test, not a missing test.** Use `{ todo: 'OI-1: ...' }` in JS or `self.skipTest('REVIEW: ...')` in Python, so the report shows it as open.
- **Don't edit generated files by hand:** `docs/traceability.md`, `docs/09-hardware-checks.md`, `cad/out/*`, `web/dist/*`. Rerun the tool instead, and commit `cad/out/check-report.json` with any CAD change.
- **The engine stays deterministic.** No `Math.random()`, `Date.now()` or anything time-dependent inside `engine/engine.js`. Pass time in.
- **No network calls.** The service binds to 127.0.0.1 and nothing calls out (REQ-OPS-001/002). A test checks this.
- **Records are append-only.** Never change the meaning of an existing record type; add a new one.
- **Cite sources.** A number from NASA or a paper goes in [references.md](docs/references.md) with the document and section.

## Commit messages

One line saying what changed and why, in the present tense: `Fix PRC crossover offset (OI-1)`. Add detail below a blank line if the reason isn't obvious.

## Code style

- **JavaScript:** plain browser JS, no build step and no frameworks. Two-space indent. Keep functions small; reuse `act()` for any user action that writes a record.
- **Python:** standard library only in `service/` (the Pi has no internet after setup). Type hints on public functions. Hardware drivers have a `Simulated...` class so everything runs on a laptop.
- **CAD:** every dimension is a `Params` field or a named constant in `cad/tablet.py`. No magic numbers inside part functions if anyone else might need to change them.

## Asking for help

Stuck for more than an hour? Post in the issue what you tried and what happened. Someone else will usually spot it in five minutes.
