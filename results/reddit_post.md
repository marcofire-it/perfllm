# I built a small "hidden tests + code review" benchmark and ran Claude Sonnet 5, Claude Opus 4.6 and a local Qwen 3.8 27B (Unsloth Q6) through it. Results + what actually separated them.

**TL;DR:** Three coding tasks of increasing difficulty (CLI log analyzer → parallel DAG task runner → full interpreter for a small language), same prompt for every model, hidden pytest suites they never saw, plus a manual code review with a fixed rubric. All three models passed 98-100% of the hidden tests. The ranking was decided almost entirely by robustness on inputs *outside* the tests and by code quality. Final weighted score: **Sonnet 5: 95.0 · Opus 4.6: 92.7 · Qwen 3.8 27B: 87.0**.

---

## Why I did this

Public leaderboards tell me a model solves LeetCode-style problems. They don't tell me what happens when I hand it a two-page spec with a few nasty corners, ask for a complete deliverable, and then poke at it the way a reviewer would. I wanted something I could re-run on any model, with fixed criteria, where "it passes the tests" is only half the grade.

## Setup

**Structure of the benchmark**

```
tasks/          <- the only thing the models ever see
  PROMPT.md     <- common rules (Python 3.11+, stdlib only, exact file names,
                   no questions allowed, document assumptions in NOTES.md)
  01-logstats/TASK.md
  02-dagrunner/TASK.md
  03-minilang/TASK.md
evaluation/     <- hidden from the models
  01..03/       <- pytest suites (34 + 42 + 86 tests), tagged core / edge / perf
  reference/    <- reference implementations that pass 100% (to validate the tests)
  RUBRIC.md, SCORECARD_TEMPLATE.md, TRAPS.md (the deliberately tricky spec points)
  run_eval.py   <- runs the hidden suites on a submission, writes JSON + summary
submissions/<model>/<task>/   results/<model>/<task>-scorecard.md
```

Each model worked in its own isolated folder containing only `TASK.md`, one fresh session per task, one shot, no follow-ups, no fixes. If a model asked questions instead of delivering, that counted against it (none did).

**The three tasks**

1. **`logstats` (easy)**: a CLI that parses a log format and emits JSON stats. Time filters with timezone offsets, p95 by nearest-rank, message templating, exact exit codes. Stresses careful spec reading and edge cases.
2. **`dagrunner` (medium)**: a parallel executor for a DAG of tasks with retries, timeouts, fail-fast, `skipped` vs `cancelled` propagation, deterministic start order, no busy-waiting. Stresses concurrency, graph logic and API design.
3. **`minilang` (hard)**: lexer + parser + tree-walking interpreter for a small language with closures, block scoping, lists by reference, C-style integer division, error line numbers and a CLI. Stresses building a whole system, semantics and error reporting.

Each spec has a handful of deliberate traps (e.g. `-7 / 2` must be `-3` not `-4`; `malformed` lines are counted even when they fall outside a time filter; a task that depends on a failed task is `skipped` but an unrelated one not started under fail-fast is `cancelled`).

**Scoring (0-100 per task)**

- **A. Hidden tests: 55 pts**, proportional to tests passed
- **B. Spec/instruction adherence: 15 pts** (exact names, no external deps, complete files, undocumented deviations)
- **C. Code quality: 15 pts**
- **D. Robustness beyond the tests: 10 pts**, same set of hand-made probes for every model (BOM, unicode, non-UTF-8 bytes, huge inputs, 1000-deep recursion, self-referencing lists, `KeyboardInterrupt` inside a worker, etc.)
- **E. NOTES.md honesty + the model's own tests: 5 pts**

Overall score = (T1 + 2·T2 + 3·T3) / 6, so the hard task counts three times the easy one.

**Models and settings**

- Claude Sonnet 5 and Claude Opus 4.6 (API)
- Qwen 3.8 27B, run locally: Unsloth **Q6** quantization, 131k context window
- Reasoning effort set to **high** for all three
- The whole evaluation side was handed to **Claude Fable 5.1, effort high**: it wrote the task specs, the hidden test suites and the reference implementations, then graded the manual sections (B-E) as a reviewer, with all three submissions for a task graded side by side so the same defect gets the same penalty. Yes, that's a Claude writing the exam and grading two Claudes; see the caveats.

## Results

[chart 1: overall weighted score]

Per-task scores (easy / medium / hard), then the weighted total:

- **Claude Sonnet 5**: 93 / 96 / 95, weighted **95.0**
- **Claude Opus 4.6**: 88 / 96 / 92, weighted **92.7**
- **Qwen 3.8 27B (Q6)**: 97 / 91 / 81, weighted **87.0**

Hidden tests: Sonnet 162/162, Opus 162/162, Qwen 160/162. So the automated part alone is a three-way tie.

[chart 2: score per task]

[chart 3: where the points were lost]

## What actually separated them

**Sonnet 5** was the most *consistent*: never the best on a single task, never a bad one either. On the interpreter it was the only model that turned a Python `RecursionError` into a clean language-level error, and the only one that handled every `OSError` in the CLI. Its NOTES.md files were the most honest and matched the code in all three tasks.

**Opus 4.6** wrote the most readable code (typed AST nodes, uniform error helpers) and by far the biggest self-written test suites (104 tests for the interpreter, 51 for the DAG runner). It lost points on robustness: the log analyzer's `main()` is a 130-line monolith that crashes on non-Latin characters when stdout is a Windows cp1252 console and on non-UTF-8 bytes in the input; the interpreter lets `RecursionError` and `ValueError` escape as raw Python exceptions.

**Qwen 3.8 27B** *won the easy task* (only model that survived every unicode/encoding probe) and then fell apart on the hard one. The interpreter has a general semantic bug: variable lookup does `env.get(name) is not None`, so any variable holding `nil` is reported as undeclared. Built-ins index `args[0]` without checking arity, so `len()` raises a raw `IndexError` instead of the language's runtime error. NOTES.md claims an arity check that doesn't exist. On the DAG runner it has a missing `nonlocal`: the "stop launching" flag is never actually set and fail-fast only works because of a second, redundant mechanism. The hidden tests didn't catch that; reading the code did.

**Things all three got wrong the same way**

- Task 2: under timeout + retry, the next attempt starts while the timed-out thread is still alive, so real concurrency can exceed `max_workers`. The spec tolerates it (you can't kill a Python thread), but nobody flagged the consequence in their notes.
- Task 3: Opus and Sonnet accept non-ASCII identifiers via `str.isalpha()`; the spec says `[A-Za-z_]`.
- Task 1: everyone treats a UTF-8 BOM as a malformed first line. Unspecified, so no penalty.

## Caveats (please read before quoting the numbers)

1. **n = 1.** One run per model per task. Differences under ~3 points are noise.
2. **The examiner and the grader are Claude (Fable 5.1, effort high).** It wrote the tests and it graded sections B-E (45 of 100 points), which are judgments. I mitigated it by grading the three submissions of each task side by side against a written rubric and by citing line numbers for every deduction, but it's still one reviewer, and it's from the same family as two of the contestants. The full scorecards are in the repo if you want to disagree with a specific call.
3. **The cp1252 crash** that cost Opus and Sonnet points on task 1 is a Windows-console artifact. With `PYTHONIOENCODING=utf-8` both pass. Removing that probe doesn't change the ranking.
4. **Ceiling effect.** 98-100% on hidden tests means these tasks are too easy for current frontier models on the *functional* axis. Round 2 will use deliberately incomplete specs, refactoring of existing buggy code, and tighter performance budgets.
5. Everything is Python stdlib-only, so this says nothing about other languages or about tool/agent workflows.
6. Qwen ran as a Q6 quant on local hardware. Some of the gap to the two API models may be quantization loss rather than the base model; I didn't test the unquantized weights.

## What I'd take away

- For the "does it work" question, all three are interchangeable on tasks of this size.
- The gap shows up in what a senior reviewer looks at: does it die on weird input, is the code maintainable, do the notes tell the truth. That's where a 27B open model at Q6 is still visibly behind, and where Sonnet 5 edged out Opus 4.6 in this round.
- Hidden tests are necessary but nowhere near sufficient. Qwen's `nil`-variable bug and the missing `nonlocal` are the kind of thing that ships and bites you in month two.

Everything is on GitHub, MIT licensed: task specs, hidden test suites, reference solutions, the harness, the three models' untouched submissions, the scorecards and the charts: https://github.com/marcofire-it/perfllm

Run your own model through it (`python evaluation/arena.py prepare <model>` builds the isolated work folders) and post the numbers. Suggestions for harder round-2 tasks very welcome.
