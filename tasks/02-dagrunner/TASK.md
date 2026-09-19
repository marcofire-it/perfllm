# Task 02 — `dagrunner`: parallel executor for tasks with dependencies

**Level: 2 (medium)** · Files to deliver: `dagrunner.py`, `NOTES.md`

## Goal

Implement a module `dagrunner.py` (standard library only) that executes a set of tasks
organised as a directed acyclic graph (DAG), in parallel with threads, respecting dependencies,
with retries, timeouts and failure propagation.

## Public API (mandatory names)

```python
class DagError(Exception): ...
class DuplicateTaskError(DagError): ...
class UnknownDependencyError(DagError): ...
class CycleError(DagError): ...

class RunResult:
    status: dict[str, str]        # name -> "success" | "failed" | "skipped" | "cancelled"
    results: dict[str, Any]       # name -> returned value (only for "success" tasks)
    errors: dict[str, BaseException]  # name -> last exception (only for "failed" tasks)
    order: list[str]              # task names in the order they were STARTED
    attempts: dict[str, int]      # name -> number of executions attempted (0 if never started)

    @property
    def ok(self) -> bool: ...     # True if every task is "success"

class DAG:
    def add_task(self, name: str, fn, deps=(), *, retries: int = 0, timeout: float | None = None) -> None: ...
    def topological_order(self) -> list[str]: ...
    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult: ...
```

## Semantics

### `add_task`
- `name`: non-empty, unique string. A duplicate name raises `DuplicateTaskError` **immediately**.
- `fn`: callable with signature `fn(deps: dict[str, Any]) -> Any`. It receives a dictionary
  `{dependency_name: result}` with the results of **all and only** its direct dependencies.
- `deps`: iterable of names. Dependencies may be referenced **before** they are defined
  (validation happens in `run()` / `topological_order()`).
- `retries`: number of **re-attempts** after the first failure (`retries=2` ⇒ up to 3 executions). Must be ≥ 0.
- `timeout`: maximum seconds for a single execution, `None` = no limit.
- Invalid values (empty `name`, `retries < 0`, `timeout <= 0`, non-callable `fn`) raise `ValueError`.

### `topological_order()`
- Raises `UnknownDependencyError` if a task depends on an undefined name,
  `CycleError` if the graph contains a cycle (including a self-loop).
- Returns a **deterministic** topological order: Kahn's algorithm where, among the tasks
  available at the same time, the one added first (insertion order) is always chosen.
- Executes nothing.

### `run(max_workers, fail_fast)`
- Validates the graph as above **before** starting any task: if there are errors it raises the exception
  and no `fn` must have been called.
- `max_workers` must be ≥ 1 (otherwise `ValueError`). There must never be more than
  `max_workers` tasks running concurrently.
- A task is started as soon as **all** its dependencies are `success` and a worker is free.
  When several tasks are ready, they are started in insertion order.
- `order` records the order in which each started task was **started** (first attempt).
- If `fn` raises an exception it is retried up to `retries` more times. If the last attempt also
  fails: `status = "failed"`, `errors[name]` = last exception, `attempts[name]` = attempts made.
- **Timeout**: if an execution exceeds `timeout` seconds it must be considered failed with a
  `TimeoutError` exception (it counts as an attempt; retries apply). Interrupting the thread is not required,
  but `run()` must not wait beyond the timeout to decide that the attempt has failed.
  Any value returned by a timed-out execution must be ignored.
- **Propagation**: every task that depends (directly or transitively) on a `failed` task
  becomes `skipped` (never started, `attempts = 0`).
- **`fail_fast=True`** (default): after the first definitive failure no new tasks are started;
  those already running are awaited until they finish (or until their timeout). Tasks not started that
  do **not** depend on the failed task have `status = "cancelled"`; those that depend on it have `"skipped"`.
- **`fail_fast=False`**: tasks independent of the failure continue normally.
- `run()` is re-runnable: subsequent calls on the same `DAG` produce a new, independent `RunResult`.
- An empty DAG returns a `RunResult` with empty dictionaries and `ok == True`.
- `run()` must always terminate (no deadlock), even with `max_workers=1` and failing tasks.

### Thread-safety
The caller does not use `DAG` from multiple threads. But the `fn`s run in different threads: `RunResult` must be
consistent when `run()` returns.

## Example

```python
from dagrunner import DAG

dag = DAG()
dag.add_task("fetch", lambda d: [1, 2, 3])
dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
dag.add_task("log", lambda d: print("fetched", d["fetch"]), deps=["fetch"])

r = dag.run(max_workers=2)
assert r.ok
assert r.results["sum"] == 12
assert r.order[0] == "fetch"
assert set(r.order[1:3]) == {"double", "log"}
```

## Constraints

- Standard library only (`threading`, `concurrent.futures`, `queue`, etc. are allowed).
- No busy-waiting (looping on `sleep`) for synchronisation.
- The module must not print anything.
