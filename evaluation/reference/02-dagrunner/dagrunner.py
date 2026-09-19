"""dagrunner — implementazione di riferimento per il Task 02.

Esecutore parallelo di task organizzati in un DAG, con retry, timeout e
propagazione dei fallimenti. Sola libreria standard.
"""
from __future__ import annotations

import heapq
import itertools
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable


class DagError(Exception):
    """Errore generico del DAG."""


class DuplicateTaskError(DagError):
    """Nome di task già presente."""


class UnknownDependencyError(DagError):
    """Un task dipende da un nome non definito."""


class CycleError(DagError):
    """Il grafo contiene un ciclo."""


class RunResult:
    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.results: dict[str, Any] = {}
        self.errors: dict[str, BaseException] = {}
        self.order: list[str] = []
        self.attempts: dict[str, int] = {}

    @property
    def ok(self) -> bool:
        return all(s == "success" for s in self.status.values())

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return f"RunResult(status={self.status!r}, order={self.order!r})"


class _Task:
    __slots__ = ("name", "fn", "deps", "retries", "timeout", "index")

    def __init__(self, name: str, fn: Callable, deps: tuple[str, ...],
                 retries: int, timeout: float | None, index: int) -> None:
        self.name = name
        self.fn = fn
        self.deps = deps
        self.retries = retries
        self.timeout = timeout
        self.index = index


class DAG:
    def __init__(self) -> None:
        self._tasks: dict[str, _Task] = {}

    # ------------------------------------------------------------------ build
    def add_task(self, name: str, fn: Callable[[dict[str, Any]], Any],
                 deps: Iterable[str] = (), *, retries: int = 0,
                 timeout: float | None = None) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("name deve essere una stringa non vuota")
        if not callable(fn):
            raise ValueError("fn deve essere callable")
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise ValueError("retries deve essere un intero >= 0")
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
                raise ValueError("timeout deve essere > 0 oppure None")
        dep_list = list(dict.fromkeys(deps))  # dedup preservando l'ordine
        for d in dep_list:
            if not isinstance(d, str) or not d:
                raise ValueError("ogni dipendenza deve essere una stringa non vuota")
        if name in self._tasks:
            raise DuplicateTaskError(f"task duplicato: {name!r}")
        self._tasks[name] = _Task(name, fn, tuple(dep_list), retries,
                                  None if timeout is None else float(timeout),
                                  len(self._tasks))

    # --------------------------------------------------------------- validate
    def _validate(self) -> None:
        for t in self._tasks.values():
            for d in t.deps:
                if d not in self._tasks:
                    raise UnknownDependencyError(
                        f"il task {t.name!r} dipende da {d!r} che non esiste")

    def topological_order(self) -> list[str]:
        self._validate()
        tasks = self._tasks
        indeg = {n: len(t.deps) for n, t in tasks.items()}
        dependents: dict[str, list[str]] = {n: [] for n in tasks}
        for t in tasks.values():
            for d in t.deps:
                dependents[d].append(t.name)
        heap = [(t.index, n) for n, t in tasks.items() if indeg[n] == 0]
        heapq.heapify(heap)
        out: list[str] = []
        while heap:
            _, n = heapq.heappop(heap)
            out.append(n)
            for m in dependents[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    heapq.heappush(heap, (tasks[m].index, m))
        if len(out) != len(tasks):
            raise CycleError("il grafo contiene un ciclo")
        return out

    # -------------------------------------------------------------------- run
    def run(self, max_workers: int = 4, fail_fast: bool = True) -> RunResult:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers deve essere >= 1")
        self.topological_order()  # valida (unknown deps / cicli) prima di eseguire
        return _Run(self._tasks, max_workers, bool(fail_fast)).execute()


class _Run:
    """Stato di una singola esecuzione. Lo scheduler gira nel thread chiamante;
    i worker comunicano tramite una coda di messaggi ("start"/"done")."""

    def __init__(self, tasks: dict[str, _Task], max_workers: int, fail_fast: bool) -> None:
        self.tasks = tasks
        self.max_workers = max_workers
        self.fail_fast = fail_fast
        self.res = RunResult()
        self.res.attempts = {n: 0 for n in tasks}
        self.status: dict[str, str | None] = {n: None for n in tasks}
        self.dependents: dict[str, list[str]] = {n: [] for n in tasks}
        for t in tasks.values():
            for d in t.deps:
                self.dependents[d].append(t.name)
        self.q: queue.Queue = queue.Queue()
        self.inflight: dict[int, list] = {}   # token -> [name, start_time|None]
        self.stale: set[int] = set()          # token scaduti (thread ancora vivo)
        self.occupied = 0                     # tentativi sottomessi e non ancora terminati
        self.started: set[str] = set()
        self.failed_any = False
        self.seq = itertools.count()
        self.ex: ThreadPoolExecutor | None = None

    # -- helpers
    def _submit(self, name: str) -> None:
        token = next(self.seq)
        t = self.tasks[name]
        deps_results = {d: self.res.results[d] for d in t.deps}
        q = self.q

        def wrapper() -> None:
            q.put(("start", token, time.monotonic()))
            try:
                r = t.fn(deps_results)
            except BaseException as e:  # noqa: BLE001 - vogliamo catturare tutto
                q.put(("done", token, False, e))
            else:
                q.put(("done", token, True, r))

        self.inflight[token] = [name, None]
        self.occupied += 1
        self.res.attempts[name] += 1
        assert self.ex is not None
        self.ex.submit(wrapper)

    def _mark_failed(self, name: str, exc: BaseException) -> None:
        self.status[name] = "failed"
        self.res.errors[name] = exc
        self.failed_any = True
        stack = list(self.dependents[name])
        while stack:
            d = stack.pop()
            if self.status[d] is None:
                self.status[d] = "skipped"
                stack.extend(self.dependents[d])

    def _attempt_failed(self, name: str, exc: BaseException) -> None:
        if self.res.attempts[name] <= self.tasks[name].retries:
            self._submit(name)  # retry
        else:
            self._mark_failed(name, exc)

    def _ready(self) -> list[str]:
        st = self.status
        return [n for n, t in self.tasks.items()
                if st[n] is None and n not in self.started
                and all(st[d] == "success" for d in t.deps)]

    def _live_inflight(self) -> bool:
        return any(tok not in self.stale for tok in self.inflight)

    def _next_deadline(self) -> float | None:
        now = time.monotonic()
        best: float | None = None
        for tok, (name, st) in self.inflight.items():
            if tok in self.stale or st is None:
                continue
            to = self.tasks[name].timeout
            if to is None:
                continue
            rem = st + to - now
            best = rem if best is None else min(best, rem)
        return best

    def _expire_timeouts(self) -> bool:
        now = time.monotonic()
        expired = []
        for tok, (name, st) in self.inflight.items():
            if tok in self.stale or st is None:
                continue
            to = self.tasks[name].timeout
            if to is not None and now - st >= to:
                expired.append((tok, name, to))
        for tok, name, to in expired:
            self.stale.add(tok)
            self._attempt_failed(name, TimeoutError(
                f"il task {name!r} ha superato il timeout di {to} s"))
        return bool(expired)

    # -- main loop
    def execute(self) -> RunResult:
        res = self.res
        if not self.tasks:
            res.status = {}
            return res
        self.ex = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            while True:
                if not (self.fail_fast and self.failed_any):
                    for n in self._ready():
                        if self.occupied >= self.max_workers:
                            break
                        self.started.add(n)
                        res.order.append(n)
                        self._submit(n)
                if not self._live_inflight():
                    break
                if self._expire_timeouts():
                    continue
                wait_for = self._next_deadline()
                try:
                    msg = self.q.get(timeout=wait_for)
                except queue.Empty:
                    continue  # deadline scaduta: gestita in cima al loop
                kind, token = msg[0], msg[1]
                if kind == "start":
                    if token in self.inflight:
                        self.inflight[token][1] = msg[2]
                    continue
                # "done"
                self.occupied -= 1
                entry = self.inflight.pop(token, None)
                if entry is None:
                    continue
                if token in self.stale:
                    self.stale.discard(token)  # risultato ignorato
                    continue
                name = entry[0]
                ok, payload = msg[2], msg[3]
                if ok:
                    self.status[name] = "success"
                    res.results[name] = payload
                else:
                    self._attempt_failed(name, payload)
        finally:
            self.ex.shutdown(wait=False)
        for n, s in self.status.items():
            res.status[n] = s if s is not None else "cancelled"
        return res


__all__ = ["DAG", "RunResult", "DagError", "DuplicateTaskError",
           "UnknownDependencyError", "CycleError"]
