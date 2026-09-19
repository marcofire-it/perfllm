# Evaluation rubric

Score per (model, task): **0–100**. The same rubric applies to every level; the level weighs in the
final average (see the end).

## A. Functional correctness — 55 points (automatic)

From `run_eval.py`. Points = 55 × (tests passed / total tests). Markers help you read the result,
they do not change the weight:

| marker | what it measures |
|---|---|
| core | functionality explicitly required by the spec |
| edge | edge cases, errors, input validation |
| perf | performance and concurrency |

Formula: `A = round(55 * passed / total)`. If the required file is missing or the module does not import:
`A = 0` and the task scores **0 overall** (submission not evaluable), regardless of the rest.

## B. Adherence to the spec and the instructions — 15 points (manual)

Start from 15 and subtract:
- -5: file / class / function / CLI option names different from the required ones (even if it "works" with adjustments)
- -5: external dependencies, or use of `eval`/`exec` where forbidden, or spurious output (debug prints, logs)
- -3: response format not respected (partial files, "..." in the code, missing files such as NOTES.md)
- -2: interpretations of the spec **not** documented in NOTES.md when the spec was clear
- -1..-3: minor deviations (JSON key order, error messages on stdout instead of stderr, etc.) not already covered by the tests

Minimum 0.

## C. Code quality — 15 points (manual)

| points | description |
|---|---|
| 13-15 | clear structure, small functions with precise responsibilities, explicit names, no duplication, explicit error handling, sensible type hints |
| 9-12 | readable and reasonable, a few long functions or some duplication, somewhat ad hoc error handling |
| 5-8 | works but is hard to follow: tangled logic, global variables, `except: pass`, misleading comments |
| 0-4 | confusing code, rewriting would be easier than modifying |

Check in particular: exception handling (never silence generic exceptions), absence of mutable global
state, files/threads closed, thread correctness (locks where needed).

## D. Robustness beyond the tests — 10 points (manual)

Try by hand 3-5 inputs **not** covered by the hidden tests (make them up on the spot: huge inputs, unicode,
odd names, option combinations, unexpected call orders). Scale:
- 10: withstands everything, behaviour consistent with the spirit of the spec
- 6-9: one minor failure (ugly message, questionable but non-crashing behaviour)
- 2-5: crash or wrong result on reasonable inputs
- 0-1: obviously fragile

## E. Communication: NOTES.md and own tests — 5 points (manual)

- 2: NOTES.md present, honest, with real assumptions and limits (not marketing)
- 1: the declared assumptions match the code
- 2: own tests present, runnable and non-trivial (they cover errors, not only the happy path). 1 if present but superficial.

## Total and aggregation

`Task total = A + B + C + D + E` (0-100).

Overall model score, weighted by difficulty:

```
Score = (1 * T01 + 2 * T02 + 3 * T03) / 6
```

Always report the three separate scores as well: a model can be excellent on the easy task and collapse on
the hard one, and that is exactly what we want to see.

## Qualitative signals to note (no points, but they belong in the comment)

- Did it "cheat" by adapting the problem (e.g. ignored the timeout because "impossible with threads")?
- Did it invent unrequested requirements (feature creep) at the expense of the required ones?
- Did it handle the deliberately tricky parts of the spec? The known traps are listed in `TRAPS.md`.
- Consistency between what NOTES.md declares and what the code does.
- Did it ask questions instead of delivering (violation of rule 4 of the prompt)?

## Evaluation procedure (checklist for the grader)

1. `python evaluation/run_eval.py --model <m> --task <t>` for section A.
2. Read the delivered code and NOTES.md in full (and `raw_response.md` if present).
3. Fill in `SCORECARD_TEMPLATE.md` as `results/<m>/<t>-scorecard.md`.
4. Run the model's own tests, if any (`python -m pytest submissions/<m>/<t>/` or `python -m unittest`).
5. Manual probes for section D, recording input and result in the scorecard.
6. Update `results/LEADERBOARD.md` (models x tasks table + weighted Score).
