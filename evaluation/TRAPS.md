# Known traps in the specs (internal use, do NOT give to the models)

Points of the spec that are deliberately easy to get wrong. Useful for the comment in the scorecard.

## 01-logstats
- `malformed` counts lines outside the filter **too**; `total` does not.
- Empty or whitespace-only lines: neither total nor malformed.
- Timestamps with an offset: comparison and output in UTC; `first/last` in `...Z` format.
- `p95` nearest-rank (not interpolated like `statistics.quantiles` or numpy).
- `latency_ms=abc` and `latency_ms=-5`: token ignored but the line stays valid.
- Message template: removal of **all** `k=v` tokens, whitespace collapsing; empty template included.
- `top_messages` ordering: count desc, then message asc; `--top 0` yields an empty list.
- Exit code 2 (file) vs 1 (arguments); nothing on stdout on error. `--top abc` must give 1:
  anyone using argparse without intercepting `SystemExit` gets 2.
- `FATAL` is not an allowed level, hence a malformed line.
- Large file: no O(n²) on templates, no repeated sorts.

## 02-dagrunner
- Validation (cycle, unknown dependency) **before** running any fn.
- `retries` = additional attempts (retries=2 means 3 attempts); `attempts` counts executions.
- Timeout with threads: the thread cannot be killed, but the status must be decided when the timeout
  expires and a late return value must be ignored. Many implementations wait for the thread (acceptable)
  or ignore the timeout altogether (no).
- `skipped` (depends on a failed task) vs `cancelled` (independent but not started because of fail_fast).
- With fail_fast, tasks **in progress** must be awaited and recorded with their real outcome.
- Deterministic start order among ready tasks (insertion order), Kahn with a stable FIFO queue.
- `fn` receives only the **direct** dependencies.
- `run()` re-runnable without leftover state. Empty DAG.
- No busy-wait: `while not done: sleep(0.01)` is an explicit violation.
- Deadlock with max_workers=1 and failures (worker never released, event never signalled).

## 03-minilang
- `/` truncates toward zero and `%` follows the dividend: using Python's `//` and `%` is wrong on negatives.
- `if (1)` is an error; `1 == "1"` is `false` without error; `1 < "a"` is an error.
- Real short-circuit (right operand not evaluated).
- Strings: without quotes at top level, with quotes inside lists; `<function>`.
- Re-`let` in the same scope is an error; in an inner scope it is shadowing. Assigning without `let` is an error.
- Closures by reference (counter), two closures from two calls are independent.
- Lists shared by reference; `list + list` creates a new list.
- Negative indices. `range(-1)` empty list.
- Error line: the one of the failing expression, inside the function, not of the call.
- `err.output` with the partial output; the CLI prints the partial output on stdout before the error.
- `break`/`return` out of context are **ParseError** (static), not runtime.
- Recursion 200: without `setrecursionlimit` a typical tree-walker blows up with RecursionError.
- Importable without side effects (no top-level code reading argv).
- Built-ins can be shadowed: `let len = 3;` in an inner scope must work.
- Performance: 300k iterations; interpreters that re-tokenize or copy environments at every block fail.

## Known ambiguities in the specs (do NOT penalise: the tests avoid them)
- 01: `=x` / `x=` tokens (equals sign at start/end): behaviour undefined. `--help` unspecified.
- 02: with fail_fast, retries of an already started task after another definitive failure: undefined.
  Diamond with max_workers=1: the independent task may end up `cancelled` or `success` depending on timing.
- 03: `let range = 7;` at top level (re-let of a builtin in the global scope); unknown escapes (`"\q"`);
  line of a ParseError at EOF with a trailing newline; whether a function body opens a scope separate from the
  parameters; error line for expressions spanning several lines.
