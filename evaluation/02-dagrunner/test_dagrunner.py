"""Test nascosti per il Task 02 (dagrunner)."""
import threading
import time

import pytest
from conftest import load_module_from


@pytest.fixture(scope="module")
def dr(submission_dir):
    return load_module_from(submission_dir, "dagrunner.py")


def run_guarded(dag, timeout=15.0, **kw):
    """Esegue dag.run(**kw) in un thread daemon: se non torna entro `timeout`
    il test fallisce invece di bloccare l'intera suite."""
    box = {}

    def target():
        try:
            box["result"] = dag.run(**kw)
        except BaseException as e:  # noqa: BLE001
            box["exc"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        pytest.fail(f"run() non è tornata entro {timeout} s (deadlock?)")
    if "exc" in box:
        raise box["exc"]
    return box["result"]


class Counter:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0
        self.current = 0
        self.peak = 0

    def enter(self):
        with self.lock:
            self.calls += 1
            self.current += 1
            self.peak = max(self.peak, self.current)

    def leave(self):
        with self.lock:
            self.current -= 1


# =========================================================================== core

@pytest.mark.core
def test_example_from_spec(dr):
    dag = dr.DAG()
    dag.add_task("fetch", lambda d: [1, 2, 3])
    dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
    dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
    dag.add_task("log", lambda d: None, deps=["fetch"])
    r = run_guarded(dag, max_workers=2)
    assert r.ok
    assert r.results["sum"] == 12
    assert r.order[0] == "fetch"
    assert set(r.order[1:3]) == {"double", "log"}
    assert r.order[3] == "sum"
    assert r.status == {n: "success" for n in ("fetch", "double", "sum", "log")}
    assert r.attempts == {"fetch": 1, "double": 1, "sum": 1, "log": 1}
    assert r.errors == {}


@pytest.mark.core
def test_deps_dict_contains_exactly_direct_deps(dr):
    seen = {}
    dag = dr.DAG()
    dag.add_task("a", lambda d: "A")
    dag.add_task("b", lambda d: "B", deps=["a"])
    def rec(key, value):
        def fn(d):
            seen[key] = dict(d)
            return value
        return fn

    dag.add_task("c", rec("c", "C"), deps=["b"])
    dag.add_task("d", rec("d", "D"), deps=["a", "b"])
    dag.add_task("e", rec("e", "E"))
    r = run_guarded(dag)
    assert r.ok
    assert seen["c"] == {"b": "B"}          # non deve contenere "a" (transitiva)
    assert seen["d"] == {"a": "A", "b": "B"}
    assert seen["e"] == {}
    assert r.results == {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}


@pytest.mark.core
def test_topological_order_insertion_tiebreak(dr):
    dag = dr.DAG()
    dag.add_task("b", lambda d: 0)
    dag.add_task("a", lambda d: 0)
    dag.add_task("c", lambda d: 0, deps=["a", "b"])
    assert dag.topological_order() == ["b", "a", "c"]


@pytest.mark.core
def test_topological_order_forward_dependency_and_kahn_fifo(dr):
    dag = dr.DAG()
    dag.add_task("x", lambda d: 0, deps=["y"])   # dipendenza definita dopo
    dag.add_task("y", lambda d: 0)
    dag.add_task("z", lambda d: 0)
    # pronti: y, z -> y (inserito prima). Poi x diventa pronto: x (idx 0) batte z (idx 2)
    assert dag.topological_order() == ["y", "x", "z"]


@pytest.mark.core
def test_topological_order_larger(dr):
    dag = dr.DAG()
    dag.add_task("build", lambda d: 0, deps=["compile", "assets"])
    dag.add_task("deploy", lambda d: 0, deps=["build", "test"])
    dag.add_task("compile", lambda d: 0, deps=["fetch"])
    dag.add_task("assets", lambda d: 0)
    dag.add_task("fetch", lambda d: 0)
    dag.add_task("test", lambda d: 0, deps=["compile"])
    # pronti iniziali (per inserimento): assets(3), fetch(4)
    # assets -> nulla; fetch -> compile(2) pronto; compile -> build? no (assets ok, compile ok -> build(0) pronto), test(5) pronto
    assert dag.topological_order() == ["assets", "fetch", "compile", "build", "test", "deploy"]


@pytest.mark.core
def test_topological_order_does_not_execute(dr):
    calls = []
    dag = dr.DAG()
    dag.add_task("a", lambda d: calls.append("a"))
    dag.topological_order()
    assert calls == []


@pytest.mark.core
def test_cycle_error_three_nodes_before_any_execution(dr):
    calls = []
    dag = dr.DAG()
    dag.add_task("root", lambda d: calls.append("root"))
    dag.add_task("a", lambda d: calls.append("a"), deps=["c"])
    dag.add_task("b", lambda d: calls.append("b"), deps=["a"])
    dag.add_task("c", lambda d: calls.append("c"), deps=["b"])
    with pytest.raises(dr.CycleError):
        dag.topological_order()
    with pytest.raises(dr.CycleError):
        run_guarded(dag)
    assert calls == []


@pytest.mark.core
def test_self_loop_is_cycle(dr):
    calls = []
    dag = dr.DAG()
    dag.add_task("a", lambda d: calls.append("a"), deps=["a"])
    with pytest.raises(dr.CycleError):
        run_guarded(dag)
    assert calls == []


@pytest.mark.core
def test_unknown_dependency_before_any_execution(dr):
    calls = []
    dag = dr.DAG()
    dag.add_task("a", lambda d: calls.append("a"))
    dag.add_task("b", lambda d: calls.append("b"), deps=["nope"])
    with pytest.raises(dr.UnknownDependencyError):
        dag.topological_order()
    with pytest.raises(dr.UnknownDependencyError):
        run_guarded(dag)
    assert calls == []


@pytest.mark.core
def test_duplicate_task_error_raised_immediately(dr):
    dag = dr.DAG()
    dag.add_task("a", lambda d: 0)
    with pytest.raises(dr.DuplicateTaskError):
        dag.add_task("a", lambda d: 1)


@pytest.mark.core
def test_exception_hierarchy(dr):
    assert issubclass(dr.DuplicateTaskError, dr.DagError)
    assert issubclass(dr.UnknownDependencyError, dr.DagError)
    assert issubclass(dr.CycleError, dr.DagError)
    assert issubclass(dr.DagError, Exception)


@pytest.mark.core
@pytest.mark.parametrize("kwargs", [
    {"name": "", "fn": lambda d: 0},
    {"name": "a", "fn": lambda d: 0, "retries": -1},
    {"name": "a", "fn": lambda d: 0, "timeout": 0},
    {"name": "a", "fn": lambda d: 0, "timeout": -1.5},
    {"name": "a", "fn": 42},
], ids=["empty-name", "negative-retries", "timeout-zero", "timeout-negative", "fn-not-callable"])
def test_add_task_value_errors(dr, kwargs):
    dag = dr.DAG()
    with pytest.raises(ValueError):
        dag.add_task(**kwargs)


@pytest.mark.core
def test_run_max_workers_zero_is_value_error(dr):
    dag = dr.DAG()
    dag.add_task("a", lambda d: 0)
    with pytest.raises(ValueError):
        dag.run(max_workers=0)


@pytest.mark.core
def test_retries_then_success(dr):
    state = {"n": 0}

    def flaky(d):
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError(f"fail {state['n']}")
        return "ok"

    dag = dr.DAG()
    dag.add_task("flaky", flaky, retries=2)
    dag.add_task("after", lambda d: d["flaky"] + "!", deps=["flaky"])
    r = run_guarded(dag)
    assert r.ok
    assert r.attempts["flaky"] == 3
    assert r.results["flaky"] == "ok"
    assert r.results["after"] == "ok!"
    assert "flaky" not in r.errors


@pytest.mark.core
def test_retries_exhausted_keeps_last_exception(dr):
    state = {"n": 0}

    def always_fail(d):
        state["n"] += 1
        raise ValueError(f"attempt {state['n']}")

    dag = dr.DAG()
    dag.add_task("bad", always_fail, retries=1)
    r = run_guarded(dag)
    assert not r.ok
    assert r.status["bad"] == "failed"
    assert r.attempts["bad"] == 2
    assert isinstance(r.errors["bad"], ValueError)
    assert str(r.errors["bad"]) == "attempt 2"
    assert "bad" not in r.results


@pytest.mark.core
def test_no_retries_by_default(dr):
    state = {"n": 0}

    def boom(d):
        state["n"] += 1
        raise RuntimeError("x")

    dag = dr.DAG()
    dag.add_task("boom", boom)
    r = run_guarded(dag)
    assert r.status["boom"] == "failed"
    assert r.attempts["boom"] == 1
    assert state["n"] == 1


@pytest.mark.core
def test_skipped_propagates_transitively(dr):
    calls = []
    dag = dr.DAG()
    dag.add_task("a", lambda d: (_ for _ in ()).throw(RuntimeError("a failed")))
    dag.add_task("b", lambda d: calls.append("b"), deps=["a"])
    dag.add_task("c", lambda d: calls.append("c"), deps=["b"])
    r = run_guarded(dag, fail_fast=False)
    assert r.status == {"a": "failed", "b": "skipped", "c": "skipped"}
    assert r.attempts == {"a": 1, "b": 0, "c": 0}
    assert r.order == ["a"]
    assert calls == []
    assert set(r.errors) == {"a"}


@pytest.mark.core
def test_fail_fast_cancels_unstarted_independent_tasks(dr):
    calls = []

    def fail(d):
        raise RuntimeError("boom")

    dag = dr.DAG()
    dag.add_task("fail", fail)
    dag.add_task("indep", lambda d: calls.append("indep"))
    dag.add_task("child", lambda d: calls.append("child"), deps=["fail"])
    r = run_guarded(dag, max_workers=1, fail_fast=True)
    assert r.status == {"fail": "failed", "indep": "cancelled", "child": "skipped"}
    assert r.attempts["indep"] == 0 and r.attempts["child"] == 0
    assert calls == []
    assert r.order == ["fail"]
    assert not r.ok


@pytest.mark.core
def test_no_fail_fast_independent_tasks_still_run(dr):
    def fail(d):
        raise RuntimeError("boom")

    dag = dr.DAG()
    dag.add_task("fail", fail)
    dag.add_task("indep", lambda d: "ran")
    dag.add_task("child", lambda d: "never", deps=["fail"])
    dag.add_task("indep2", lambda d: d["indep"] + "!", deps=["indep"])
    r = run_guarded(dag, max_workers=1, fail_fast=False)
    assert r.status == {"fail": "failed", "indep": "success", "child": "skipped", "indep2": "success"}
    assert r.results == {"indep": "ran", "indep2": "ran!"}
    assert r.order == ["fail", "indep", "indep2"]


@pytest.mark.core
def test_running_task_is_awaited_when_another_fails(dr):
    def slow(d):
        time.sleep(0.4)
        return "slow-done"

    def fail(d):
        raise RuntimeError("boom")

    dag = dr.DAG()
    dag.add_task("slow", slow)
    dag.add_task("fail", fail)
    r = run_guarded(dag, max_workers=2, fail_fast=True)
    assert r.status["slow"] == "success"
    assert r.results["slow"] == "slow-done"
    assert r.status["fail"] == "failed"


@pytest.mark.core
def test_timeout_marks_failed_with_timeout_error(dr):
    def sleepy(d):
        time.sleep(1.0)
        return "late"

    dag = dr.DAG()
    dag.add_task("sleepy", sleepy, timeout=0.2)
    dag.add_task("child", lambda d: 1, deps=["sleepy"])
    t0 = time.monotonic()
    r = run_guarded(dag)
    elapsed = time.monotonic() - t0
    assert r.status["sleepy"] == "failed"
    assert isinstance(r.errors["sleepy"], TimeoutError)
    assert r.status["child"] == "skipped"
    assert r.attempts["sleepy"] == 1
    assert "sleepy" not in r.results
    assert elapsed < 1.5, f"run() ha impiegato {elapsed:.2f}s"


@pytest.mark.core
def test_timeout_with_retries(dr):
    calls = Counter()

    def sleepy(d):
        calls.enter()
        try:
            time.sleep(0.6)
        finally:
            calls.leave()
        return "late"

    dag = dr.DAG()
    dag.add_task("sleepy", sleepy, timeout=0.15, retries=1)
    r = run_guarded(dag, max_workers=2)
    assert r.status["sleepy"] == "failed"
    assert r.attempts["sleepy"] == 2
    assert isinstance(r.errors["sleepy"], TimeoutError)
    time.sleep(1.5)  # attende i thread residui
    assert calls.calls == 2


@pytest.mark.core
def test_timed_out_return_value_is_ignored(dr):
    def sleepy(d):
        time.sleep(0.5)
        return 42

    dag = dr.DAG()
    dag.add_task("sleepy", sleepy, timeout=0.1)
    r = run_guarded(dag)
    assert r.status["sleepy"] == "failed"
    assert "sleepy" not in r.results
    time.sleep(0.8)  # anche dopo che il thread ha finito
    assert "sleepy" not in r.results
    assert r.status["sleepy"] == "failed"


@pytest.mark.core
def test_timeout_not_triggered_for_fast_task(dr):
    dag = dr.DAG()
    dag.add_task("fast", lambda d: "ok", timeout=2.0)
    r = run_guarded(dag)
    assert r.ok
    assert r.results["fast"] == "ok"
    assert r.attempts["fast"] == 1


# =========================================================================== edge

@pytest.mark.edge
def test_empty_dag(dr):
    dag = dr.DAG()
    assert dag.topological_order() == []
    r = run_guarded(dag)
    assert r.ok is True
    assert r.status == {} and r.results == {} and r.errors == {}
    assert r.order == [] and r.attempts == {}


@pytest.mark.edge
def test_ok_false_when_any_failed_and_results_exclude_non_success(dr):
    def fail(d):
        raise KeyError("k")

    dag = dr.DAG()
    dag.add_task("good", lambda d: 1)
    dag.add_task("bad", fail, deps=["good"])
    dag.add_task("skip", lambda d: 2, deps=["bad"])
    r = run_guarded(dag, fail_fast=False)
    assert r.ok is False
    assert set(r.results) == {"good"}
    assert set(r.errors) == {"bad"}
    assert isinstance(r.errors["bad"], KeyError)
    assert set(r.status) == {"good", "bad", "skip"}


@pytest.mark.edge
def test_run_is_reexecutable_with_independent_results(dr):
    state = {"n": 0}

    def count(d):
        state["n"] += 1
        return state["n"]

    dag = dr.DAG()
    dag.add_task("c", count)
    dag.add_task("d", lambda d: d["c"] * 10, deps=["c"])
    r1 = run_guarded(dag)
    r2 = run_guarded(dag)
    assert r1 is not r2
    assert r1.results == {"c": 1, "d": 10}
    assert r2.results == {"c": 2, "d": 20}
    assert r1.order == r2.order == ["c", "d"]
    assert r1.attempts == r2.attempts == {"c": 1, "d": 1}


@pytest.mark.edge
def test_diamond_with_failure_no_deadlock(dr):
    def fail(d):
        raise RuntimeError("b")

    dag = dr.DAG()
    dag.add_task("a", lambda d: 1)
    dag.add_task("b", fail, deps=["a"])
    dag.add_task("c", lambda d: 3, deps=["a"])
    dag.add_task("d", lambda d: 4, deps=["b", "c"])
    r = run_guarded(dag, timeout=5.0, max_workers=1, fail_fast=False)
    assert r.status == {"a": "success", "b": "failed", "c": "success", "d": "skipped"}
    r2 = run_guarded(dag, timeout=5.0, max_workers=1, fail_fast=True)
    assert r2.status["a"] == "success" and r2.status["b"] == "failed"
    assert r2.status["d"] == "skipped"
    assert r2.status["c"] in ("cancelled", "success")


@pytest.mark.edge
def test_order_records_start_order_serial(dr):
    dag = dr.DAG()
    dag.add_task("late", lambda d: 0, deps=["early2"])
    dag.add_task("early1", lambda d: 0)
    dag.add_task("early2", lambda d: 0)
    dag.add_task("mid", lambda d: 0, deps=["early1"])
    r = run_guarded(dag, max_workers=1)
    assert r.ok
    assert r.order == dag.topological_order() == ["early1", "early2", "late", "mid"]


@pytest.mark.edge
def test_order_only_contains_started_tasks_once(dr):
    state = {"n": 0}

    def flaky(d):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("once")
        return "ok"

    dag = dr.DAG()
    dag.add_task("flaky", flaky, retries=3)
    dag.add_task("after", lambda d: 1, deps=["flaky"])
    r = run_guarded(dag)
    assert r.ok
    assert r.order == ["flaky", "after"]  # i retry non duplicano la voce
    assert r.attempts["flaky"] == 2


@pytest.mark.edge
def test_status_has_all_tasks_even_with_fail_fast(dr):
    def fail(d):
        raise RuntimeError("x")

    dag = dr.DAG()
    names = [f"t{i}" for i in range(10)]
    dag.add_task("fail", fail)
    for n in names:
        dag.add_task(n, lambda d: 0, deps=["fail"] if n.endswith(("1", "3")) else [])
    r = run_guarded(dag, max_workers=1, fail_fast=True)
    assert set(r.status) == {"fail", *names}
    assert r.status["fail"] == "failed"
    for n in names:
        expected = "skipped" if n.endswith(("1", "3")) else "cancelled"
        assert r.status[n] == expected, n
        assert r.attempts[n] == 0
    assert set(r.attempts) == set(r.status)


@pytest.mark.edge
def test_deps_accepts_any_iterable_and_string_dep_names(dr):
    dag = dr.DAG()
    dag.add_task("a", lambda d: 1)
    dag.add_task("b", lambda d: 2)
    dag.add_task("c", lambda d: d["a"] + d["b"], deps=("a", "b"))
    dag.add_task("e", lambda d: d["c"] * 2, deps=iter(["c"]))
    r = run_guarded(dag)
    assert r.ok and r.results["e"] == 6


@pytest.mark.edge
def test_base_exception_subclass_is_captured(dr):
    class Weird(BaseException):
        pass

    def weird(d):
        raise Weird()

    dag = dr.DAG()
    dag.add_task("w", weird)
    dag.add_task("after", lambda d: 1, deps=["w"])
    r = run_guarded(dag)
    assert r.status == {"w": "failed", "after": "skipped"}
    assert isinstance(r.errors["w"], Weird)


# =========================================================================== perf

@pytest.mark.perf
def test_real_parallelism(dr):
    def slow(d):
        time.sleep(0.3)
        return 1

    dag = dr.DAG()
    for i in range(4):
        dag.add_task(f"t{i}", slow)
    t0 = time.monotonic()
    r = run_guarded(dag, max_workers=4)
    elapsed = time.monotonic() - t0
    assert r.ok
    assert elapsed < 0.7, f"4 task da 0.3s con 4 worker hanno impiegato {elapsed:.2f}s"


@pytest.mark.perf
def test_max_workers_is_respected(dr):
    c = Counter()

    def work(d):
        c.enter()
        try:
            time.sleep(0.1)
        finally:
            c.leave()
        return 1

    dag = dr.DAG()
    for i in range(6):
        dag.add_task(f"t{i}", work)
    r = run_guarded(dag, max_workers=2)
    assert r.ok
    assert c.calls == 6
    assert c.peak <= 2, f"concorrenza massima osservata: {c.peak}"
    assert c.peak == 2, "con 2 worker e 6 task indipendenti ci si aspetta 2 esecuzioni concorrenti"


@pytest.mark.perf
def test_serial_execution_follows_topological_order(dr):
    executed = []
    lock = threading.Lock()

    def make(name):
        def fn(d):
            with lock:
                executed.append(name)
            return name
        return fn

    dag = dr.DAG()
    dag.add_task("d", make("d"), deps=["b", "c"])
    dag.add_task("b", make("b"), deps=["a"])
    dag.add_task("c", make("c"), deps=["a"])
    dag.add_task("a", make("a"))
    dag.add_task("e", make("e"))
    r = run_guarded(dag, max_workers=1)
    assert r.ok
    # Kahn: pronti a(3), e(4) -> a; poi b(1), c(2) battono e(4); dopo c e' pronto d(0) che batte e(4)
    assert executed == dag.topological_order() == ["a", "b", "c", "d", "e"]
    assert r.order == executed


@pytest.mark.perf
def test_chain_of_200_tasks(dr):
    dag = dr.DAG()
    dag.add_task("t0", lambda d: 0)
    for i in range(1, 200):
        dag.add_task(f"t{i}", (lambda i: lambda d: d[f"t{i-1}"] + 1)(i), deps=[f"t{i-1}"])
    t0 = time.monotonic()
    r = run_guarded(dag, timeout=20.0, max_workers=4)
    elapsed = time.monotonic() - t0
    assert r.ok
    assert r.results["t199"] == 199
    assert r.order == [f"t{i}" for i in range(200)]
    assert elapsed < 5.0, f"catena di 200 task: {elapsed:.2f}s"


@pytest.mark.perf
def test_500_independent_tasks(dr):
    dag = dr.DAG()
    for i in range(500):
        dag.add_task(f"t{i}", (lambda i: lambda d: i)(i))
    t0 = time.monotonic()
    r = run_guarded(dag, timeout=20.0, max_workers=8)
    elapsed = time.monotonic() - t0
    assert r.ok
    assert len(r.results) == 500 and r.results["t499"] == 499
    assert sorted(r.order) == sorted(f"t{i}" for i in range(500))
    assert elapsed < 5.0, f"500 task indipendenti: {elapsed:.2f}s"
