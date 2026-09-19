# perfllm: a small "hidden tests + code review" benchmark for LLM coding

Three coding tasks of increasing difficulty, one identical prompt for every model, hidden pytest
suites the models never see, and a manual code review against a fixed rubric. The point is to grade
what a senior reviewer would grade, not only "does it pass the tests".

**Round 1 (2026-09-19):** Claude Sonnet 5, Claude Opus 4.6 and a local Qwen 3.8 27B (Unsloth Q6,
131k context), all at reasoning effort *high*. All three passed 98-100% of the hidden tests; the
ranking came from robustness beyond the tests and from code quality. See `results/LEADERBOARD.md`
and the write-up in `results/reddit_post.md`.

| Model | Task 1 (easy) | Task 2 (medium) | Task 3 (hard) | Weighted |
|---|---|---|---|---|
| Claude Sonnet 5 | 93 | 96 | 95 | **95.0** |
| Claude Opus 4.6 | 88 | 96 | 92 | **92.7** |
| Qwen 3.8 27B (Q6) | 97 | 91 | 81 | **87.0** |

> **Contamination notice.** Everything is public, including the hidden tests and the reference
> solutions. From the moment this repo went online, round-1 results cannot be reproduced fairly on
> models trained after that date. Round 2 will use fresh tasks.

## Layout

```
perfllm/
├── tasks/                    <- the ONLY thing a model ever sees
│   ├── PROMPT.md             <- common rules, prepended to every task
│   ├── 01-logstats/TASK.md   <- level 1 (easy): log analyzer CLI
│   ├── 02-dagrunner/TASK.md  <- level 2 (medium): parallel DAG task runner
│   ├── 03-minilang/TASK.md   <- level 3 (hard): interpreter for a small language
│   └── it/                   <- original Italian specs used in round 1
├── evaluation/               <- hidden from the models
│   ├── RUBRIC.md             <- scoring criteria and weights
│   ├── SCORECARD_TEMPLATE.md <- per (model, task) review sheet
│   ├── TRAPS.md              <- the deliberately tricky points of each spec
│   ├── run_eval.py           <- runs the hidden suites on a submission
│   ├── arena.py              <- creates isolated work folders for the models, collects results
│   ├── split_response.py     <- extracts files from a raw chat response
│   ├── 01-logstats/          <- 34 tests + fixtures
│   ├── 02-dagrunner/         <- 42 tests
│   ├── 03-minilang/          <- 86 tests + 19 programs with expected output
│   └── reference/            <- reference implementations (pass 100%, validate the tests)
├── submissions/<model>/<task-id>/   <- what each model delivered, untouched
└── results/                         <- test JSON, scorecards, leaderboard, charts, write-up
```

All tasks require **Python 3.11+ and the standard library only**, so results are comparable and
the suites run without dependencies. Evaluation needs `pytest`.

## The tasks

| ID | Name | Level | What it stresses |
|----|------|-------|------------------|
| 01 | logstats | easy | careful spec reading, edge cases, CLI conventions |
| 02 | dagrunner | medium | concurrency, graph logic, failure propagation, API design |
| 03 | minilang | hard | lexer/parser/evaluator, closures, scoping, error reporting, robustness |

## Scoring (0-100 per task)

- **A. Hidden tests, 55 pts**: proportional to tests passed (automatic).
- **B. Spec and instruction adherence, 15 pts**: exact names, no external deps, complete files, undocumented deviations.
- **C. Code quality, 15 pts**.
- **D. Robustness beyond the tests, 10 pts**: the same hand-made probes for every model.
- **E. NOTES.md honesty and the model's own tests, 5 pts**.

Overall score per model = (T01 + 2·T02 + 3·T03) / 6. Full rubric in `evaluation/RUBRIC.md`.

## Running it on a model

1. Create the work folders (outside this repo, so a model with filesystem access cannot read `evaluation/`):
   ```
   python evaluation/arena.py prepare <model-name> [<model-name> ...]
   ```
   This writes `../perfllm-arena/<model>/<task-id>/TASK.md` (prompt + spec merged) and prints the
   sentence to give each model.
2. One fresh session per (model, task), one shot, no follow-ups. Agentic tools write the files in
   place; chat UIs get the content pasted and the reply saved as `raw_response.md` in that folder.
3. Collect and run the hidden suites:
   ```
   python evaluation/arena.py collect --all
   python evaluation/run_eval.py --all
   ```
   Results land in `results/<model>/<task-id>.json` and `results/summary.md`.
4. Manual review: fill `evaluation/SCORECARD_TEMPLATE.md` per (model, task) following the rubric,
   grading all submissions of the same task side by side so the same defect gets the same penalty.

To validate the suites against the reference solutions:
```
python evaluation/run_eval.py --model _reference
```

## How round 1 was run

- The task specs, hidden tests, reference implementations, rubric and the manual review (sections
  B-E) were all produced by Claude Fable 5.1 at effort *high*, acting as examiner and grader. Yes,
  that is a Claude writing the exam and grading two Claudes; the scorecards cite line numbers for
  every deduction so each call can be disputed.
- Round 1 used the Italian specs in `tasks/it/`; the English ones in `tasks/` are faithful
  translations made afterwards for publication. The scorecards in `results/` are in Italian, as
  written during the review.
- One run per model per task. Differences under about 3 points are noise.

## License

MIT. Model outputs in `submissions/` are published as delivered, for transparency.
