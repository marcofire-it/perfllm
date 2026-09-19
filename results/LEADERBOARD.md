# Leaderboard, round 1 (2026-09-19)

Models: Claude Sonnet 5 (`sonnet`), Claude Opus 4.6 (`opus`), Qwen 3.8 27B Unsloth Q6 131k context (`qwen`).
All at reasoning effort *high*. Rubric: `evaluation/RUBRIC.md`. Details in `results/<model>/<task>-scorecard.md`
(scorecards are in Italian, as written during the review).

## Final score (weighted 1:2:3 by difficulty)

| Rank | Model | 01-logstats | 02-dagrunner | 03-minilang | **Score** |
|---|---|---|---|---|---|
| 1 | **sonnet** | 93 | 96 | 95 | **95.0** |
| 2 | **opus** | 88 | 96 | 92 | **92.7** |
| 3 | **qwen** | 97 | 91 | 81 | **87.0** |

`Score = (T01 + 2*T02 + 3*T03) / 6`

## Hidden tests (section A)

| Model | 01 (34) | 02 (42) | 03 (86) |
|---|---|---|---|
| opus | 34 | 42 | 86 |
| sonnet | 34 | 42 | 86 |
| qwen | 34 | 42 | 84 |

The automatic tests alone do not separate the models: the difference comes from the manual sections
(adherence, code quality, robustness beyond the tests, honesty of the notes).

## Per-section detail (A/B/C/D/E out of 55/15/15/10/5)

| Model | 01-logstats | 02-dagrunner | 03-minilang |
|---|---|---|---|
| opus | 55/15/10/3/5 | 55/14/13/9/5 | 55/14/13/5/5 |
| sonnet | 55/15/13/5/5 | 55/14/13/9/5 | 55/14/13/8/5 |
| qwen | 55/14/13/10/5 | 55/13/10/9/4 | 54/12/8/3/4 |

## What decided the ranking

**sonnet** is the most consistent: never the best on a single task, never a bad one either. On the hard
task it is the only one that converts a `RecursionError` into a clean MiniLang error and handles every
I/O error in the CLI. Its NOTES.md files are the most honest and match the code in all three tasks.

**opus** has the most readable code (tasks 02 and 03) and the largest self-written test suites (51 tests
on task 02, 104 on task 03), but loses points on robustness: on task 01 `main` is a 130-line monolith and
the script crashes on non-Latin characters with a Windows cp1252 console and on non-UTF-8 bytes in the
file; on task 03 `RecursionError` and `ValueError` leak as raw Python exceptions.

**qwen** wins the easy task (the only one with no crash on unicode and invalid bytes) but collapses on the
hard one: a general semantic bug (variables holding `nil` are treated as undeclared, because the lookup
uses `get(name) is not None`), built-ins without arity checks that raise raw `IndexError`, an AST made of
positional tuples that is hard to follow, and a NOTES.md that claims an arity check the code does not have.
On task 02 it has a missing `nonlocal`: the stop flag is never set and fail-fast only works thanks to a
second mechanism.

## Defects shared by all three

- Task 02: under timeout + retry, the next attempt starts while the timed-out thread is still alive, so
  real concurrency exceeds `max_workers`. The spec implicitly allows it, but nobody drew the consequences
  in their notes.
- Task 03: opus and sonnet accept non-ASCII identifiers (`isalpha()`) against the `[A-Za-z_]` spec.
- Task 01: all treat the UTF-8 BOM as a malformed first line (acceptable, unspecified).

## How to read the numbers

- The cp1252 crash (task 01, opus and sonnet) depends on the Windows evaluation environment: with
  `PYTHONIOENCODING=utf-8` both pass. Excluding that probe would raise opus and sonnet by a few points on
  task 01 and would not change the final ranking.
- Sections B/C/D/E are one grader's judgments (Claude Fable 5.1, effort high), applied side by side to the
  three models for the same task, so consistent with each other but not absolute. Gaps under 3 points are
  not significant.
- All three models passed almost 100% of the hidden tests: for the next round the difficulty should go up
  (deliberately incomplete spec, refactoring of existing buggy code, tighter performance budgets) to get
  more separation.
- Qwen ran as a Q6 quantization on local hardware; part of the gap to the two API models may be
  quantization loss rather than the base model.
