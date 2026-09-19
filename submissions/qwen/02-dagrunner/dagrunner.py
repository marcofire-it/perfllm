"""dagrunner: parallel DAG task executor (standard library only).

Executes a set of tasks organized as a directed acyclic graph in parallel
threads, honoring dependencies, per-task retries and timeouts, with
failure propagation and optional fail-fast behavior.

Public API:
    DagError, DuplicateTaskError, UnknownDependencyError, CycleError
    RunResult
    DAG
"""

from __future__ import annotations

import heapq
import threading
from collections import deque
from typing import Any, Callable

__all__ = [
    "DagError",
    "DuplicateTaskError",
    "UnknownDependencyError",
    "CycleError",
    "RunResult",
    "DAG",
]


class DagError(Exception):
    """Base class for DAG validation and execution errors."""


class DuplicateTaskError(DagError):
    """Raised when a task name is added twice."""


class UnknownDependencyError(DagError):
    """Raised when a task depends on a name that was never defined."""


class CycleError(DagError):
    """Raised when the task graph contains a cycle (including self-loops)."""


class RunResult:
    """Immutable-ish container describing the outcome of one ``DAG.run()``."""

    def __init__(
        self,
        status: dict[str, str],
        results: dict[str, Any],
        errors: dict[str, BaseException],
        order: list[str],
        attempts: dict[str, int],
    ) -> None:
        self.status = dict(status)
        self.results = dict(results)
        self.errors = dict(errors)
        self.order = list(order)
        self.attempts = dict(attempts)

    @property
    def ok(self) -> bool:
        """True if every task finished with status ``"success"``."""
        return all(s == "success" for s in self.status.values())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RunResult(ok={self.ok}, status={self.status!r}, order={self.order!r})"


class _TaskRecord:
    """Internal storage for one task definition."""

    __slots__ = ("name", "fn", "deps", "retries", "timeout", "index")

    def __init__(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], Any],
        deps: tuple[str, ...],
        retries: int,
        timeout: float | None,
        index: int,
    ) -> None:
        self.name = name
        self.fn = fn
        self.deps = deps
        self.retries = retries
        self.timeout = timeout
        self.index = index


class DAG:
    """A directed acyclic graph of tasks, executable in parallel."""

    def __init__(self) -> None:
        self._tasks: dict[str, _TaskRecord] = {}
        self._order: list[str] = []  # insertion order of task names

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def add_task(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], Any],
        deps: Any = (),
        *,
        retries: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Register a task.

        ``fn`` is called as ``fn(deps: dict[str, Any]) -> Any`` where the
        dictionary maps each *direct* dependency name to its result.
        Dependencies may reference tasks that are added later; validation
        of dependency names happens in ``topological_order()`` / ``run()``.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("task name must be a non-empty string")
        if name in self._tasks:
            raise DuplicateTaskError(f"duplicate task name: {name!r}")
        if not callable(fn):
            raise ValueError(f"fn for task {name!r} must be callable")
        dep_list = tuple(deps)
        for dep in dep_list:
            if not isinstance(dep, str) or not dep:
                raise ValueError(
                    f"dependencies of task {name!r} must be non-empty strings, "
                    f"got {dep!r}"
                )
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise ValueError(f"retries for task {name!r} must be an int >= 0")
        if timeout is not None:
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or timeout <= 0
            ):
                raise ValueError(f"timeout for task {name!r} must be > 0 or None")

        self._tasks[name] = _TaskRecord(name, fn, dep_list, retries, timeout, len(self._order))
        self._order.append(name)

    # ------------------------------------------------------------------ #
    # Validation / ordering
    # ------------------------------------------------------------------ #

    def _validate_unknown_deps(self) -> None:
        for name in self._order:
            for dep in self._tasks[name].deps:
                if dep not in self._tasks:
                    raise UnknownDependencyError(
                        f"task {name!r} depends on unknown task {dep!r}"
                    )

    def topological_order(self) -> list[str]:
        """Return a deterministic topological order (Kahn's algorithm).

        Among the tasks that are simultaneously available, the one added
        first (insertion order) is always chosen.  Raises
        ``UnknownDependencyError`` or ``CycleError`` on invalid graphs.
        Does not execute any task.
        """
        self._validate_unknown_deps()
        indegree = {name: 0 for name in self._order}
        dependents: dict[str, list[str]] = {name: [] for name in self._order}
        for name in self._order:
            for dep in self._tasks[name].deps:
                indegree[name] += 1
                dependents[dep].append(name)

        heap = [(self._tasks[name].index, name) for name in self._order if indegree[name] == 0]
        heapq.heapify(heap)
        result: list[str] = []
        while heap:
            _, name = heapq.heappop(heap)
            result.append(name)
            for follower in dependents[name]:
                indegree[follower] -= 1
                if indegree[follower] == 0:
                    heapq.heappush(heap, (self._tasks[follower].index, follower))

        if len(result) != len(self._order):
            raise CycleError("task graph contains a cycle")
        return result

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult:
        """Execute the DAG in parallel and return a fresh :class:`RunResult`."""
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be an integer >= 1")

        # Full validation before starting anything: no fn may be called on error.
        self.topological_order()

        names = list(self._order)
        if not names:
            return RunResult({}, {}, {}, [], {})

        dependents: dict[str, list[str]] = {name: [] for name in names}
        for name in names:
            for dep in self._tasks[name].deps:
                dependents[dep].append(name)

        cond = threading.Condition()
        state: dict[str, str] = {name: "pending" for name in names}
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        attempts: dict[str, int] = {name: 0 for name in names}
        order: list[str] = []
        queue: deque[tuple[str, dict[str, Any]]] = deque()
        ready: list[tuple[int, str]] = []
        in_flight = 0          # launched but not yet completed
        stop_launching = False  # fail_fast triggered
        shutdown = False

        for name in names:
            if not self._tasks[name].deps:
                ready.append((self._tasks[name].index, name))
        heapq.heapify(ready)

        def on_success(name: str) -> None:
            for follower in dependents[name]:
                if (
                    state[follower] == "pending"
                    and all(state[d] == "success" for d in self._tasks[follower].deps)
                ):
                    heapq.heappush(ready, (self._tasks[follower].index, follower))

        def on_failure(name: str) -> None:
            # Propagate: every transitive dependent becomes "skipped".
            stack = list(dependents[name])
            while stack:
                follower = stack.pop()
                if state[follower] == "pending":
                    state[follower] = "skipped"
                    stack.extend(dependents[follower])
            if fail_fast:
                stop_launching = True
                for name2 in names:
                    if state[name2] == "pending":
                        state[name2] = "cancelled"

        def execute(name: str, deps_results: dict[str, Any]) -> None:
            nonlocal in_flight
            rec = self._tasks[name]
            max_attempts = rec.retries + 1
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                holder: dict[str, Any] = {}

                def _run() -> None:
                    try:
                        holder["value"] = rec.fn(deps_results)
                    except BaseException as exc:  # noqa: BLE001 - re-raised below
                        holder["error"] = exc

                t = threading.Thread(target=_run, daemon=True)
                t.start()
                if rec.timeout is None:
                    t.join()
                    timed_out = False
                else:
                    t.join(rec.timeout)
                    timed_out = t.is_alive()

                if timed_out:
                    # Thread is left running (not required to be killed);
                    # its eventual result, if any, is ignored.
                    last_exc = TimeoutError(
                        f"task {name!r} exceeded timeout of {rec.timeout}s"
                    )
                elif "error" in holder:
                    last_exc = holder["error"]
                else:
                    with cond:
                        attempts[name] = attempt
                        state[name] = "success"
                        results[name] = holder["value"]
                        in_flight -= 1
                        on_success(name)
                        cond.notify_all()
                    return

            with cond:
                attempts[name] = max_attempts
                state[name] = "failed"
                errors[name] = last_exc
                in_flight -= 1
                on_failure(name)
                cond.notify_all()

        def worker() -> None:
            while True:
                with cond:
                    while not queue and not shutdown:
                        cond.wait()
                    if not queue:
                        return
                    name, deps_results = queue.popleft()
                execute(name, deps_results)

        workers = [
            threading.Thread(target=worker, daemon=True, name=f"dagrunner-worker-{i}")
            for i in range(max_workers)
        ]
        for w in workers:
            w.start()

        terminal = ("success", "failed", "skipped", "cancelled")
        with cond:
            while True:
                if not stop_launching:
                    while ready and in_flight < max_workers:
                        _, name = heapq.heappop(ready)
                        if state[name] != "pending":
                            continue
                        rec = self._tasks[name]
                        state[name] = "running"
                        order.append(name)
                        attempts[name] = 1
                        in_flight += 1
                        deps_results = {d: results[d] for d in rec.deps}
                        queue.append((name, deps_results))
                    cond.notify_all()  # wake workers for the newly queued tasks
                if all(state[name] in terminal for name in names):
                    break
                cond.wait()
            shutdown = True
            cond.notify_all()

        for w in workers:
            w.join()

        return RunResult(state, results, errors, order, attempts)
