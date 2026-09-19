"""dagrunner.py — esecutore parallelo di task organizzati come DAG.

Sola libreria standard. Vedi TASK.md e NOTES.md per la specifica completa e
le scelte di design.
"""

from __future__ import annotations

import heapq
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #

class DagError(Exception):
    """Errore base per il modulo dagrunner."""


class DuplicateTaskError(DagError):
    """Sollevata quando si aggiunge un task con un nome già usato."""


class UnknownDependencyError(DagError):
    """Sollevata quando un task dipende da un nome non definito."""


class CycleError(DagError):
    """Sollevata quando il grafo delle dipendenze contiene un ciclo."""


# --------------------------------------------------------------------------- #
# Risultato dell'esecuzione
# --------------------------------------------------------------------------- #

@dataclass
class RunResult:
    status: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, BaseException] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    attempts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(s == "success" for s in self.status.values())


# --------------------------------------------------------------------------- #
# DAG
# --------------------------------------------------------------------------- #

class _TaskSpec:
    __slots__ = ("name", "fn", "deps", "retries", "timeout")

    def __init__(self, name: str, fn: Callable[[dict[str, Any]], Any],
                 deps: tuple[str, ...], retries: int, timeout: Optional[float]):
        self.name = name
        self.fn = fn
        self.deps = deps
        self.retries = retries
        self.timeout = timeout


class DAG:
    def __init__(self) -> None:
        self._tasks: dict[str, _TaskSpec] = {}
        self._order: list[str] = []          # ordine di inserimento (nomi)
        self._insertion_index: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    def add_task(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], Any],
        deps: Iterable[str] = (),
        *,
        retries: int = 0,
        timeout: Optional[float] = None,
    ) -> None:
        if not isinstance(name, str) or name == "":
            raise ValueError("name deve essere una stringa non vuota")
        if name in self._tasks:
            raise DuplicateTaskError(f"Task '{name}' già definito")
        if not callable(fn):
            raise ValueError("fn deve essere callable")
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            raise ValueError("retries deve essere un intero >= 0")
        if timeout is not None:
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
                raise ValueError("timeout deve essere None oppure un numero > 0")

        deps_tuple = tuple(dict.fromkeys(deps))  # dedup preservando l'ordine

        spec = _TaskSpec(name, fn, deps_tuple, retries, timeout)
        self._insertion_index[name] = len(self._order)
        self._order.append(name)
        self._tasks[name] = spec

    # ------------------------------------------------------------------ #
    def _build_graph(self) -> tuple[dict[str, int], dict[str, list[str]]]:
        tasks = self._tasks
        for name, spec in tasks.items():
            for d in spec.deps:
                if d not in tasks:
                    raise UnknownDependencyError(
                        f"Il task '{name}' dipende dal task sconosciuto '{d}'"
                    )
        indegree = {name: len(spec.deps) for name, spec in tasks.items()}
        dependents: dict[str, list[str]] = {name: [] for name in tasks}
        for name, spec in tasks.items():
            for d in spec.deps:
                dependents[d].append(name)
        return indegree, dependents

    # ------------------------------------------------------------------ #
    def topological_order(self) -> list[str]:
        indegree, dependents = self._build_graph()
        idx = self._insertion_index

        heap: list[tuple[int, str]] = []
        for name in self._order:
            if indegree[name] == 0:
                heapq.heappush(heap, (idx[name], name))

        remaining = dict(indegree)
        order: list[str] = []
        while heap:
            _, n = heapq.heappop(heap)
            order.append(n)
            for m in dependents[n]:
                remaining[m] -= 1
                if remaining[m] == 0:
                    heapq.heappush(heap, (idx[m], m))

        if len(order) != len(self._tasks):
            raise CycleError("Il grafo delle dipendenze contiene un ciclo")
        return order

    # ------------------------------------------------------------------ #
    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult:
        if not isinstance(max_workers, int) or isinstance(max_workers, bool) or max_workers < 1:
            raise ValueError("max_workers deve essere un intero >= 1")

        # Valida l'intero grafo (nomi sconosciuti / cicli) PRIMA di eseguire
        # qualunque cosa: se questa chiamata solleva, nessun fn è stato invocato.
        self.topological_order()

        tasks = self._tasks
        names = list(self._order)
        if not names:
            return RunResult(status={}, results={}, errors={}, order=[], attempts={})

        indegree, dependents = self._build_graph()
        idx = self._insertion_index

        remaining_deps: dict[str, set[str]] = {n: set(tasks[n].deps) for n in names}
        status: dict[str, Optional[str]] = {n: None for n in names}
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        attempts: dict[str, int] = {n: 0 for n in names}
        order: list[str] = []

        ready_heap: list[tuple[int, str]] = []
        for n in names:
            if not remaining_deps[n]:
                heapq.heappush(ready_heap, (idx[n], n))

        finished_q: "queue.Queue[tuple[str, bool, Any, Optional[BaseException], int]]" = queue.Queue()
        active_count = 0
        failed_occurred = False

        def worker(name: str, spec: _TaskSpec) -> None:
            deps_snapshot = {d: results[d] for d in spec.deps}
            attempt_count = 0
            last_exc: Optional[BaseException] = None
            result: Any = None
            success = False

            for _attempt in range(spec.retries + 1):
                attempt_count += 1
                try:
                    if spec.timeout is None:
                        result = spec.fn(deps_snapshot)
                        success = True
                        last_exc = None
                        break

                    box: dict[str, Any] = {}

                    def _target(box: dict[str, Any] = box, fn=spec.fn,
                                dsnap=deps_snapshot) -> None:
                        try:
                            box["result"] = fn(dsnap)
                        except BaseException as exc:  # noqa: BLE001
                            box["exc"] = exc

                    t = threading.Thread(target=_target, daemon=True)
                    t.start()
                    t.join(spec.timeout)
                    if t.is_alive():
                        last_exc = TimeoutError(
                            f"Task '{name}' scaduto dopo {spec.timeout}s "
                            f"(tentativo {attempt_count})"
                        )
                        continue
                    if "exc" in box:
                        last_exc = box["exc"]
                        continue
                    result = box.get("result")
                    success = True
                    last_exc = None
                    break
                except BaseException as exc:  # noqa: BLE001
                    last_exc = exc
                    continue

            finished_q.put((name, success, result, last_exc, attempt_count))

        def launch(name: str) -> None:
            nonlocal active_count
            spec = tasks[name]
            status[name] = "running"
            order.append(name)
            active_count += 1
            threading.Thread(target=worker, args=(name, spec), daemon=True).start()

        def propagate_skip(failed_name: str) -> None:
            stack = list(dependents.get(failed_name, ()))
            while stack:
                n = stack.pop()
                if status[n] is not None:
                    continue
                status[n] = "skipped"
                stack.extend(dependents.get(n, ()))

        while True:
            while (
                active_count < max_workers
                and ready_heap
                and not (fail_fast and failed_occurred)
            ):
                _, name = heapq.heappop(ready_heap)
                if status[name] is not None:
                    continue
                launch(name)

            if active_count == 0:
                break

            name, success, result, exc, attempt_count = finished_q.get()
            active_count -= 1
            attempts[name] = attempt_count

            if success:
                status[name] = "success"
                results[name] = result
                for m in dependents.get(name, ()):
                    if status[m] is not None:
                        continue
                    remaining_deps[m].discard(name)
                    if not remaining_deps[m]:
                        heapq.heappush(ready_heap, (idx[m], m))
            else:
                status[name] = "failed"
                errors[name] = exc  # type: ignore[assignment]
                failed_occurred = True
                propagate_skip(name)

        for n in names:
            if status[n] is None:
                status[n] = "cancelled"

        final_status: dict[str, str] = {n: status[n] for n in names}  # type: ignore[misc]
        return RunResult(
            status=final_status,
            results=results,
            errors=errors,
            order=order,
            attempts=attempts,
        )
