"""dagrunner.py — Parallel DAG task runner with retries, timeouts, and failure propagation."""

from __future__ import annotations

import heapq
import queue
import threading
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DagError(Exception):
    """Base exception for DAG errors."""


class DuplicateTaskError(DagError):
    """Raised when a task with a duplicate name is added."""


class UnknownDependencyError(DagError):
    """Raised when a task depends on an undefined task."""


class CycleError(DagError):
    """Raised when the DAG contains a cycle (including self-loops)."""


# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------

class RunResult:
    """Immutable result of a single DAG execution."""

    __slots__ = ("status", "results", "errors", "order", "attempts")

    def __init__(
        self,
        status: dict[str, str],
        results: dict[str, Any],
        errors: dict[str, BaseException],
        order: list[str],
        attempts: dict[str, int],
    ) -> None:
        self.status = status
        self.results = results
        self.errors = errors
        self.order = order
        self.attempts = attempts

    @property
    def ok(self) -> bool:
        """True if every task finished with status 'success'."""
        return all(s == "success" for s in self.status.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _Task:
    """Internal descriptor for a registered task."""
    __slots__ = ("name", "fn", "deps", "retries", "timeout")

    def __init__(
        self,
        name: str,
        fn: Any,
        deps: tuple[str, ...],
        retries: int,
        timeout: float | None,
    ) -> None:
        self.name = name
        self.fn = fn
        self.deps = deps
        self.retries = retries
        self.timeout = timeout


def _execute_with_timeout(fn: Any, deps_dict: dict[str, Any], timeout: float | None) -> Any:
    """Run *fn(deps_dict)* respecting an optional per-attempt *timeout*.

    If *timeout* is ``None`` the function is called directly in the current
    thread.  Otherwise a daemon helper thread is spawned; if the helper does
    not finish within *timeout* seconds a ``TimeoutError`` is raised without
    waiting for the helper to terminate (as permitted by the spec).
    """
    if timeout is None:
        return fn(deps_dict)

    result_box: list[Any] = [None]
    exc_box: list[BaseException | None] = [None]
    done_event = threading.Event()

    def _target() -> None:
        try:
            result_box[0] = fn(deps_dict)
        except BaseException as exc:
            exc_box[0] = exc
        finally:
            done_event.set()

    t = threading.Thread(target=_target, daemon=True)
    t.start()

    if done_event.wait(timeout=timeout):
        if exc_box[0] is not None:
            raise exc_box[0]
        return result_box[0]

    raise TimeoutError(f"Task timed out after {timeout}s")


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------

class DAG:
    """Directed Acyclic Graph of callable tasks with dependency tracking."""

    def __init__(self) -> None:
        self._tasks: dict[str, _Task] = {}
        self._insertion_order: list[str] = []

    # -- registration -------------------------------------------------------

    def add_task(
        self,
        name: str,
        fn: Any,
        deps: Any = (),
        *,
        retries: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Register a task.  Deps may reference tasks not yet added."""
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        if not callable(fn):
            raise ValueError("fn must be callable")
        if not isinstance(retries, int) or retries < 0:
            raise ValueError("retries must be a non-negative integer")
        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
            raise ValueError("timeout must be a positive number or None")
        if name in self._tasks:
            raise DuplicateTaskError(f"Task '{name}' already exists")

        # Deduplicate deps while preserving order
        unique_deps = tuple(dict.fromkeys(deps))
        self._tasks[name] = _Task(name, fn, unique_deps, retries, timeout)
        self._insertion_order.append(name)

    # -- topological sort ---------------------------------------------------

    def topological_order(self) -> list[str]:
        """Return a deterministic topological order (Kahn, insertion-order ties).

        Raises ``UnknownDependencyError`` or ``CycleError`` if the graph is
        invalid.
        """
        # Validate that every dependency is a known task
        for name, task in self._tasks.items():
            for dep in task.deps:
                if dep not in self._tasks:
                    raise UnknownDependencyError(
                        f"Task '{name}' depends on unknown task '{dep}'"
                    )

        # Build in-degree map and forward-adjacency (dep -> list of dependents)
        in_degree: dict[str, int] = {}
        dependents: dict[str, list[str]] = defaultdict(list)
        for name, task in self._tasks.items():
            in_degree[name] = len(task.deps)
            for dep in task.deps:
                dependents[dep].append(name)

        insertion_idx = {name: i for i, name in enumerate(self._insertion_order)}

        # Min-heap keyed by insertion index
        heap: list[tuple[int, str]] = []
        for name in self._insertion_order:
            if in_degree[name] == 0:
                heapq.heappush(heap, (insertion_idx[name], name))

        order: list[str] = []
        while heap:
            _, name = heapq.heappop(heap)
            order.append(name)
            for dep_name in dependents[name]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    heapq.heappush(heap, (insertion_idx[dep_name], dep_name))

        if len(order) != len(self._tasks):
            raise CycleError("DAG contains a cycle")

        return order

    # -- execution ----------------------------------------------------------

    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult:
        """Execute all tasks respecting dependencies, concurrency, retries, and timeouts."""
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be an integer >= 1")

        # Validate graph *before* executing anything
        self.topological_order()

        # Empty DAG
        if not self._tasks:
            return RunResult(
                status={}, results={}, errors={}, order=[], attempts={}
            )

        # ---- per-run mutable state ----------------------------------------
        status: dict[str, str] = {}
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        order_list: list[str] = []
        attempts_dict: dict[str, int] = {name: 0 for name in self._tasks}

        remaining_deps: dict[str, set[str]] = {
            name: set(task.deps) for name, task in self._tasks.items()
        }
        dependents: dict[str, list[str]] = defaultdict(list)
        for name in self._insertion_order:
            for dep in self._tasks[name].deps:
                dependents[dep].append(name)

        insertion_idx = {name: i for i, name in enumerate(self._insertion_order)}

        # Ready-heap (min-heap on insertion index)
        ready_heap: list[tuple[int, str]] = []
        for name in self._insertion_order:
            if not remaining_deps[name]:
                heapq.heappush(ready_heap, (insertion_idx[name], name))

        active_count = 0
        stop_new = False

        # Worker → coordinator channel (no busy-wait)
        comp_q: queue.Queue[tuple[str, str, Any, BaseException | None, int]] = (
            queue.Queue()
        )

        def _worker(task_name: str, task: _Task, deps_dict: dict[str, Any]) -> None:
            """Runs in a dedicated thread; always puts exactly one message."""
            try:
                max_att = 1 + task.retries
                last_exc: BaseException | None = None
                actual = 0
                for _ in range(max_att):
                    actual += 1
                    try:
                        val = _execute_with_timeout(task.fn, deps_dict, task.timeout)
                        comp_q.put(("success", task_name, val, None, actual))
                        return
                    except BaseException as exc:
                        last_exc = exc
                comp_q.put(("failed", task_name, None, last_exc, actual))
            except BaseException as exc:          # safety net
                comp_q.put(("failed", task_name, None, exc, 1))

        # ---- main coordination loop --------------------------------------
        while ready_heap or active_count > 0:
            # Launch as many ready tasks as allowed
            while ready_heap and active_count < max_workers and not stop_new:
                _, name = heapq.heappop(ready_heap)
                if name in status:
                    continue  # already skipped / cancelled
                task = self._tasks[name]
                deps_dict = {dep: results[dep] for dep in task.deps}
                order_list.append(name)
                active_count += 1
                threading.Thread(
                    target=_worker,
                    args=(name, task, deps_dict),
                    daemon=True,
                ).start()

            if active_count == 0:
                break

            # Block until a worker finishes (no busy-wait)
            evt, name, val, exc, att = comp_q.get()
            active_count -= 1

            if evt == "success":
                status[name] = "success"
                results[name] = val
                attempts_dict[name] = att
                # Unlock dependents
                for dep_name in dependents.get(name, []):
                    if dep_name in status:
                        continue
                    remaining_deps[dep_name].discard(name)
                    if not remaining_deps[dep_name] and not stop_new:
                        heapq.heappush(
                            ready_heap, (insertion_idx[dep_name], dep_name)
                        )

            else:  # "failed"
                status[name] = "failed"
                errors[name] = exc  # type: ignore[assignment]
                attempts_dict[name] = att

                # Propagate "skipped" to every transitive dependent
                to_skip: set[str] = set()
                stack = list(dependents.get(name, []))
                while stack:
                    dep_name = stack.pop()
                    if dep_name in to_skip:
                        continue
                    if dep_name in status and status[dep_name] != "cancelled":
                        continue
                    to_skip.add(dep_name)
                    stack.extend(dependents.get(dep_name, []))

                for skip_name in to_skip:
                    status[skip_name] = "skipped"
                    attempts_dict[skip_name] = 0

                # Remove skipped entries still sitting in the ready heap
                # (they will be harmlessly skipped on pop via the `in status`
                # guard, but clearing is cleaner)

                if fail_fast and not stop_new:
                    stop_new = True
                    # Cancel all remaining ready tasks that aren't already handled
                    while ready_heap:
                        _, rname = heapq.heappop(ready_heap)
                        if rname not in status:
                            status[rname] = "cancelled"
                            attempts_dict[rname] = 0

        # Final sweep: any task still without a status
        for name in self._tasks:
            if name not in status:
                status[name] = "cancelled" if stop_new else "skipped"
                attempts_dict[name] = 0

        return RunResult(
            status=status,
            results=results,
            errors=errors,
            order=order_list,
            attempts=attempts_dict,
        )
