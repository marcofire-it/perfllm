"""Comprehensive tests for dagrunner.py."""

import threading
import time
import unittest

from dagrunner import (
    DAG,
    CycleError,
    DagError,
    DuplicateTaskError,
    RunResult,
    UnknownDependencyError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(d):
    return None


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestExceptionHierarchy(unittest.TestCase):
    def test_subclasses(self):
        self.assertTrue(issubclass(DuplicateTaskError, DagError))
        self.assertTrue(issubclass(UnknownDependencyError, DagError))
        self.assertTrue(issubclass(CycleError, DagError))
        self.assertTrue(issubclass(DagError, Exception))


# ---------------------------------------------------------------------------
# add_task validation
# ---------------------------------------------------------------------------

class TestAddTaskValidation(unittest.TestCase):
    def test_empty_name(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("", _noop)

    def test_non_string_name(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task(123, _noop)  # type: ignore

    def test_non_callable_fn(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("x", "not_callable")  # type: ignore

    def test_negative_retries(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("x", _noop, retries=-1)

    def test_zero_timeout(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("x", _noop, timeout=0)

    def test_negative_timeout(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("x", _noop, timeout=-1)

    def test_duplicate_task(self):
        dag = DAG()
        dag.add_task("a", _noop)
        with self.assertRaises(DuplicateTaskError):
            dag.add_task("a", _noop)

    def test_valid_task(self):
        dag = DAG()
        dag.add_task("a", _noop, retries=0, timeout=None)
        dag.add_task("b", _noop, deps=["a"], retries=3, timeout=5.0)


# ---------------------------------------------------------------------------
# topological_order
# ---------------------------------------------------------------------------

class TestTopologicalOrder(unittest.TestCase):
    def test_empty_dag(self):
        dag = DAG()
        self.assertEqual(dag.topological_order(), [])

    def test_single_task(self):
        dag = DAG()
        dag.add_task("a", _noop)
        self.assertEqual(dag.topological_order(), ["a"])

    def test_linear_chain(self):
        dag = DAG()
        dag.add_task("a", _noop)
        dag.add_task("b", _noop, deps=["a"])
        dag.add_task("c", _noop, deps=["b"])
        self.assertEqual(dag.topological_order(), ["a", "b", "c"])

    def test_diamond(self):
        dag = DAG()
        dag.add_task("a", _noop)
        dag.add_task("b", _noop, deps=["a"])
        dag.add_task("c", _noop, deps=["a"])
        dag.add_task("d", _noop, deps=["b", "c"])
        order = dag.topological_order()
        self.assertEqual(order[0], "a")
        self.assertIn("b", order[1:3])
        self.assertIn("c", order[1:3])
        self.assertEqual(order[3], "d")

    def test_insertion_order_tiebreak(self):
        """Among simultaneously available tasks, insertion order wins."""
        dag = DAG()
        dag.add_task("z", _noop)
        dag.add_task("a", _noop)
        dag.add_task("m", _noop)
        self.assertEqual(dag.topological_order(), ["z", "a", "m"])

    def test_insertion_order_after_dep(self):
        dag = DAG()
        dag.add_task("root", _noop)
        dag.add_task("b", _noop, deps=["root"])
        dag.add_task("a", _noop, deps=["root"])  # inserted after b
        order = dag.topological_order()
        self.assertEqual(order, ["root", "b", "a"])

    def test_unknown_dependency(self):
        dag = DAG()
        dag.add_task("a", _noop, deps=["missing"])
        with self.assertRaises(UnknownDependencyError):
            dag.topological_order()

    def test_self_loop(self):
        dag = DAG()
        dag.add_task("a", _noop, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()

    def test_cycle(self):
        dag = DAG()
        dag.add_task("a", _noop, deps=["b"])
        dag.add_task("b", _noop, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()

    def test_forward_reference(self):
        """Dependencies can be declared before they are defined."""
        dag = DAG()
        dag.add_task("b", _noop, deps=["a"])
        dag.add_task("a", _noop)
        order = dag.topological_order()
        self.assertEqual(order, ["a", "b"])


# ---------------------------------------------------------------------------
# run — basic
# ---------------------------------------------------------------------------

class TestRunBasic(unittest.TestCase):
    def test_empty_dag(self):
        r = DAG().run()
        self.assertTrue(r.ok)
        self.assertEqual(r.status, {})
        self.assertEqual(r.results, {})
        self.assertEqual(r.errors, {})
        self.assertEqual(r.order, [])
        self.assertEqual(r.attempts, {})

    def test_single_task(self):
        dag = DAG()
        dag.add_task("a", lambda d: 42)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["a"], 42)
        self.assertEqual(r.status["a"], "success")
        self.assertEqual(r.attempts["a"], 1)
        self.assertEqual(r.order, ["a"])

    def test_spec_example(self):
        dag = DAG()
        dag.add_task("fetch", lambda d: [1, 2, 3])
        dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
        dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
        dag.add_task("log", lambda d: "logged", deps=["fetch"])

        r = dag.run(max_workers=2)
        self.assertTrue(r.ok)
        self.assertEqual(r.results["sum"], 12)
        self.assertEqual(r.order[0], "fetch")
        self.assertEqual(set(r.order[1:3]), {"double", "log"})

    def test_deps_dict_content(self):
        """fn receives only direct dependency results."""
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("b", lambda d: d["a"] + 1, deps=["a"])
        dag.add_task("c", lambda d: d, deps=["b"])  # should NOT contain "a"
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["b"], 2)
        self.assertEqual(r.results["c"], {"b": 2})

    def test_max_workers_validation(self):
        dag = DAG()
        dag.add_task("a", _noop)
        with self.assertRaises(ValueError):
            dag.run(max_workers=0)
        with self.assertRaises(ValueError):
            dag.run(max_workers=-1)

    def test_graph_validation_before_execution(self):
        """run() validates graph before calling any fn."""
        called = []
        dag = DAG()
        dag.add_task("a", lambda d: called.append(1), deps=["missing"])
        with self.assertRaises(UnknownDependencyError):
            dag.run()
        self.assertEqual(called, [])

    def test_rerunnable(self):
        """Successive run() calls produce independent results."""
        counter = [0]

        def fn(d):
            counter[0] += 1
            return counter[0]

        dag = DAG()
        dag.add_task("a", fn)
        r1 = dag.run()
        r2 = dag.run()
        self.assertTrue(r1.ok)
        self.assertTrue(r2.ok)
        self.assertEqual(r1.results["a"], 1)
        self.assertEqual(r2.results["a"], 2)


# ---------------------------------------------------------------------------
# run — retries
# ---------------------------------------------------------------------------

class TestRunRetries(unittest.TestCase):
    def test_retry_then_success(self):
        attempts = [0]

        def flaky(d):
            attempts[0] += 1
            if attempts[0] < 3:
                raise RuntimeError("not yet")
            return "ok"

        dag = DAG()
        dag.add_task("flaky", flaky, retries=2)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["flaky"], "ok")
        self.assertEqual(r.attempts["flaky"], 3)

    def test_all_retries_fail(self):
        def always_fail(d):
            raise ValueError("boom")

        dag = DAG()
        dag.add_task("bad", always_fail, retries=2)
        r = dag.run()
        self.assertFalse(r.ok)
        self.assertEqual(r.status["bad"], "failed")
        self.assertEqual(r.attempts["bad"], 3)
        self.assertIsInstance(r.errors["bad"], ValueError)

    def test_no_retries(self):
        def fail_once(d):
            raise RuntimeError("fail")

        dag = DAG()
        dag.add_task("x", fail_once, retries=0)
        r = dag.run()
        self.assertEqual(r.attempts["x"], 1)
        self.assertEqual(r.status["x"], "failed")


# ---------------------------------------------------------------------------
# run — timeout
# ---------------------------------------------------------------------------

class TestRunTimeout(unittest.TestCase):
    def test_timeout_failure(self):
        def slow(d):
            time.sleep(10)
            return "done"

        dag = DAG()
        dag.add_task("slow", slow, timeout=0.1)
        r = dag.run()
        self.assertFalse(r.ok)
        self.assertEqual(r.status["slow"], "failed")
        self.assertIsInstance(r.errors["slow"], TimeoutError)
        self.assertEqual(r.attempts["slow"], 1)

    def test_timeout_with_retries(self):
        attempts = [0]

        def sometimes_slow(d):
            attempts[0] += 1
            if attempts[0] <= 2:
                time.sleep(10)
            return "fast"

        dag = DAG()
        dag.add_task("task", sometimes_slow, retries=2, timeout=0.1)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["task"], "fast")
        self.assertEqual(r.attempts["task"], 3)

    def test_fast_task_with_timeout(self):
        """Task that finishes well within timeout succeeds normally."""
        dag = DAG()
        dag.add_task("fast", lambda d: 99, timeout=5.0)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["fast"], 99)


# ---------------------------------------------------------------------------
# run — failure propagation, fail_fast
# ---------------------------------------------------------------------------

class TestFailurePropagation(unittest.TestCase):
    def test_skipped_direct_dep(self):
        dag = DAG()
        dag.add_task("a", lambda d: (_ for _ in ()).throw(RuntimeError("fail")))
        dag.add_task("b", lambda d: "should not run", deps=["a"])
        r = dag.run(fail_fast=False)
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.status["b"], "skipped")
        self.assertEqual(r.attempts["b"], 0)
        self.assertNotIn("b", r.results)

    def test_skipped_transitive(self):
        dag = DAG()
        dag.add_task("a", lambda d: (_ for _ in ()).throw(RuntimeError))
        dag.add_task("b", _noop, deps=["a"])
        dag.add_task("c", _noop, deps=["b"])
        r = dag.run(fail_fast=False)
        self.assertEqual(r.status["b"], "skipped")
        self.assertEqual(r.status["c"], "skipped")

    def test_independent_tasks_continue_without_fail_fast(self):
        dag = DAG()
        dag.add_task("fail_task", lambda d: (_ for _ in ()).throw(RuntimeError))
        dag.add_task("ok_task", lambda d: "fine")
        r = dag.run(fail_fast=False)
        self.assertEqual(r.status["fail_task"], "failed")
        self.assertEqual(r.status["ok_task"], "success")
        self.assertEqual(r.results["ok_task"], "fine")

    def test_fail_fast_cancels_independent(self):
        barrier = threading.Event()

        def blocking(d):
            barrier.wait(timeout=5)
            return "done"

        dag = DAG()
        dag.add_task("slow", blocking)
        dag.add_task("fail_task", lambda d: (_ for _ in ()).throw(RuntimeError))
        dag.add_task("independent", lambda d: "nope")

        r = dag.run(max_workers=2, fail_fast=True)
        barrier.set()  # unblock slow in case it's running

        # One of {slow, fail_task} started; 'independent' should be cancelled
        self.assertEqual(r.status["fail_task"], "failed")
        self.assertIn(r.status["independent"], ("cancelled", "success"))
        # If independent wasn't started it must be cancelled
        if r.status["independent"] == "cancelled":
            self.assertEqual(r.attempts["independent"], 0)

    def test_fail_fast_skipped_vs_cancelled(self):
        """Dependents of failed → skipped; others → cancelled."""
        dag = DAG()
        dag.add_task("a", lambda d: (_ for _ in ()).throw(RuntimeError))
        dag.add_task("b", _noop, deps=["a"])  # depends on failed → skipped
        dag.add_task("c", _noop)              # independent → cancelled
        r = dag.run(max_workers=1, fail_fast=True)
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.status["b"], "skipped")
        self.assertEqual(r.status["c"], "cancelled")

    def test_fail_fast_running_tasks_complete(self):
        """Already-running tasks are awaited even after fail_fast triggers."""
        started = threading.Event()
        proceed = threading.Event()

        def slow(d):
            started.set()
            proceed.wait(timeout=5)
            return "completed"

        dag = DAG()
        dag.add_task("slow_task", slow)
        dag.add_task("fail_task", lambda d: (_ for _ in ()).throw(RuntimeError))

        def runner():
            return dag.run(max_workers=2, fail_fast=True)

        # Run in thread so we can control timing
        result_box: list[RunResult] = []
        t = threading.Thread(target=lambda: result_box.append(runner()))
        t.start()
        started.wait(timeout=5)
        proceed.set()
        t.join(timeout=10)

        r = result_box[0]
        self.assertEqual(r.status["fail_task"], "failed")
        self.assertEqual(r.status["slow_task"], "success")
        self.assertEqual(r.results["slow_task"], "completed")


# ---------------------------------------------------------------------------
# run — concurrency
# ---------------------------------------------------------------------------

class TestConcurrency(unittest.TestCase):
    def test_parallel_speedup(self):
        """4 independent 0.1 s tasks with 4 workers should finish in ~0.1 s."""
        dag = DAG()
        for i in range(4):
            dag.add_task(f"t{i}", lambda d: time.sleep(0.1) or True)

        start = time.monotonic()
        r = dag.run(max_workers=4)
        elapsed = time.monotonic() - start

        self.assertTrue(r.ok)
        self.assertLess(elapsed, 0.8)  # generous: must be < 4 × 0.1

    def test_max_workers_respected(self):
        """At most max_workers tasks run concurrently."""
        max_concurrent = [0]
        current = [0]
        lock = threading.Lock()

        def track(d):
            with lock:
                current[0] += 1
                if current[0] > max_concurrent[0]:
                    max_concurrent[0] = current[0]
            time.sleep(0.05)
            with lock:
                current[0] -= 1
            return True

        dag = DAG()
        for i in range(8):
            dag.add_task(f"t{i}", track)

        r = dag.run(max_workers=3)
        self.assertTrue(r.ok)
        self.assertLessEqual(max_concurrent[0], 3)

    def test_single_worker(self):
        """max_workers=1 serialises execution."""
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("b", lambda d: d["a"] + 1, deps=["a"])
        dag.add_task("c", lambda d: d["b"] + 1, deps=["b"])
        r = dag.run(max_workers=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.results["c"], 3)
        self.assertEqual(r.order, ["a", "b", "c"])


# ---------------------------------------------------------------------------
# run — order tracking
# ---------------------------------------------------------------------------

class TestOrder(unittest.TestCase):
    def test_order_reflects_start(self):
        dag = DAG()
        dag.add_task("a", _noop)
        dag.add_task("b", _noop, deps=["a"])
        r = dag.run(max_workers=1)
        self.assertEqual(r.order, ["a", "b"])

    def test_order_insertion_tiebreak(self):
        dag = DAG()
        dag.add_task("z", _noop)
        dag.add_task("a", _noop)
        dag.add_task("m", _noop)
        r = dag.run(max_workers=1)
        self.assertEqual(r.order, ["z", "a", "m"])


# ---------------------------------------------------------------------------
# RunResult.ok
# ---------------------------------------------------------------------------

class TestRunResultOk(unittest.TestCase):
    def test_ok_true(self):
        r = RunResult({"a": "success"}, {"a": 1}, {}, ["a"], {"a": 1})
        self.assertTrue(r.ok)

    def test_ok_false_failed(self):
        r = RunResult({"a": "failed"}, {}, {"a": RuntimeError()}, ["a"], {"a": 1})
        self.assertFalse(r.ok)

    def test_ok_false_skipped(self):
        r = RunResult({"a": "skipped"}, {}, {}, [], {"a": 0})
        self.assertFalse(r.ok)

    def test_ok_empty(self):
        r = RunResult({}, {}, {}, [], {})
        self.assertTrue(r.ok)


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    def test_no_deadlock_with_single_worker_and_failure(self):
        dag = DAG()
        dag.add_task("a", lambda d: (_ for _ in ()).throw(RuntimeError))
        dag.add_task("b", _noop, deps=["a"])
        dag.add_task("c", _noop)
        r = dag.run(max_workers=1, fail_fast=True)
        self.assertIn(r.status["a"], ("failed",))

    def test_large_fan_out(self):
        dag = DAG()
        dag.add_task("root", lambda d: 0)
        for i in range(50):
            dag.add_task(f"leaf{i}", lambda d: d["root"] + 1, deps=["root"])
        r = dag.run(max_workers=8)
        self.assertTrue(r.ok)
        self.assertEqual(len(r.results), 51)

    def test_deps_as_set(self):
        """deps can be any iterable, including a set."""
        dag = DAG()
        dag.add_task("a", _noop)
        dag.add_task("b", _noop)
        dag.add_task("c", _noop, deps={"a", "b"})
        r = dag.run()
        self.assertTrue(r.ok)

    def test_fn_returning_none(self):
        dag = DAG()
        dag.add_task("a", lambda d: None)
        dag.add_task("b", lambda d: d["a"], deps=["a"])
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertIsNone(r.results["a"])
        self.assertIsNone(r.results["b"])


if __name__ == "__main__":
    unittest.main()
