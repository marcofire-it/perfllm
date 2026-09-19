# results/

Produced by `evaluation/run_eval.py` plus the manual scorecards.

- `summary.md`: automatic table (test pass rates), regenerated on every run.
- `<model>/<task-id>.json`: test detail for that pair (failed tests, timings, markers).
- `<model>/<task-id>-scorecard.md`: full review following `evaluation/RUBRIC.md`.
  Round-1 scorecards are in Italian, as written during the review.
- `LEADERBOARD.md`: final ranking with the weighted score.
- `charts/`: comparison charts (PNG) and the script that regenerates them.
- `reddit_post.md`: the write-up of round 1.
- `_reference/`: the reference implementations run through the same harness (baseline: 100%).
