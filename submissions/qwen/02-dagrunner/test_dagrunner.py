"""Tests for dagrunner (unittest / pytest compatible, stdlib only)."""

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


class ExampleTest(unittest.TestCase):
    def test_task_example(self):
        dag = DAG()
        dag.add_task("fetch", lambda d: [1, 2, 3])
        dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
        dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
        dag.add_task("log", lambda d: print("fetched", d["fetch"]), deps=["fetch"])

        r = dag.run(max_workers=2)
        self.assertTrue(r.ok)
        self.assertEqual(r.results["sum"], 12)
        self.assertEqual(r.order[0], "fetch")
        self.assertEqual(set(r.order[1:3]), {"double", "log"})


class ValidationTest(unittest.TestCase):
    def test_duplicate_name(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        with self.assertRaises(DuplicateTaskError):
            dag.add_task("a", lambda d: 1)
        with self.assertRaises(DagError):
            dag.add_task("a", lambda d: 1)

    def test_empty_name(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("", lambda d: 1)

    def test_non_string_name(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task(3, lambda d: 1)

    def test_non_callable_fn(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", 42)

    def test_bad_retries(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, retries=-1)
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, retries=1.5)

    def test_bad_timeout(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, timeout=0)
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, timeout=-2)

    def test_bad_dep(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, deps=[""])

    def test_unknown_dependency(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["ghost"])
        with self.assertRaises(UnknownDependencyError):
            dag.topological_order()
        with self.assertRaises(UnknownDependencyError):
            dag.run()

    def test_cycle(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["b"])
        dag.add_task("b", lambda d: 1, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()
        with self.assertRaises(CycleError):
            dag.run()

    def test_self_loop(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()

    def test_run_validates_before_executing(self):
        dag = DAG()
        called = []
        dag.add_task("a", lambda d: called.append("a"))
        dag.add_task("b", lambda d: 1, deps=["ghost"])
        with self.assertRaises(UnknownDependencyError):
            dag.run()
        self.assertEqual(called, [])

    def test_bad_max_workers(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        with self.assertRaises(ValueError):
            dag.run(max_workers=0)
        with self.assertRaises(ValueError):
            dag.run(max_workers=-1)


class TopologicalOrderTest(unittest.TestCase):
    def test_deterministic_insertion_order(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("c", lambda d: 1, deps=["a"])
        dag.add_task("b", lambda d: 1)
        # When {b, c} become available together, c (added first) must come first.
        self.assertEqual(dag.topological_order(), ["a", "c", "b"])

    def test_full_order(self):
        dag = DAG()
        dag.add_task("z", lambda d: 1)
        dag.add_task("m", lambda d: 1, deps=["z"])
        dag.add_task("a", lambda d: 1, deps=["m"])
        self.assertEqual(dag.topological_order(), ["z", "m", "a"])

    def test_deps_addable_before_definition(self):
        dag = DAG()
        dag.add_task("child", lambda d: d["parent"], deps=["parent"])
        dag.add_task("parent", lambda d: 5)
        self.assertEqual(dag.topological_order(), ["parent", "child"])
        r = dag.run()
        self.assertEqual(r.results["child"], 5)


class RunSemanticsTest(unittest.TestCase):
    def test_empty_dag(self):
        r = DAG().run()
        self.assertIsInstance(r, RunResult)
        self.assertTrue(r.ok)
        self.assertEqual(r.status, {})
        self.assertEqual(r.results, {})
        self.assertEqual(r.errors, {})
        self.assertEqual(r.order, [])
        self.assertEqual(r.attempts, {})

    def test_deps_receive_only_direct_dependencies(self):
        dag = DAG()
        seen = {}
        dag.add_task("a", lambda d: seen.update(a=d) or 1)
        dag.add_task("b", lambda d: seen.update(b=d) or 2)
        dag.add_task("c", lambda d: seen.update(c=d) or 3, deps=["a", "b"])
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(seen["c"], {"a": 1, "b": 2})

    def test_failure_no_retry(self):
        calls = []

        def boom(_):
            calls.append(1)
            raise ValueError("nope")

        dag = DAG()
        dag.add_task("a", boom)
        r = dag.run()
        self.assertFalse(r.ok)
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.attempts["a"], 1)
        self.assertIsInstance(r.errors["a"], ValueError)
        self.assertEqual(calls, [1])
        self.assertNotIn("a", r.results)

    def test_retry_until_success(self):
        calls = []

        def flaky(_):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return "ok"

        dag = DAG()
        dag.add_task("a", flaky, retries=3)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["a"], "ok")
        self.assertEqual(r.attempts["a"], 3)

    def test_retry_exhausted(self):
        calls = []

        def always_fails(_):
            calls.append(1)
            raise RuntimeError("permanent")

        dag = DAG()
        dag.add_task("a", always_fails, retries=2)
        r = dag.run()
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.attempts["a"], 3)  # 1 + 2 retries
        self.assertEqual(len(calls), 3)
        self.assertIsInstance(r.errors["a"], RuntimeError)

    def test_timeout_counts_as_attempt_and_retries(self):
        calls = []

        def slow(_):
            calls.append(1)
            time.sleep(0.3)
            return "too late"

        dag = DAG()
        dag.add_task("a", slow, retries=1, timeout=0.1)
        start = time.monotonic()
        r = dag.run()
        elapsed = time.monotonic() - start
        self.assertEqual(r.status["a"], "failed")
        self.assertIsInstance(r.errors["a"], TimeoutError)
        self.assertEqual(r.attempts["a"], 2)
        self.assertNotIn("a", r.results)
        self.assertLess(elapsed, 1.5)  # run() did not wait for stuck threads

    def test_timeout_then_success(self):
        calls = []

        def first_slow(_):
            calls.append(1)
            if len(calls) == 1:
                time.sleep(0.3)
            return "done"

        dag = DAG()
        dag.add_task("a", first_slow, retries=1, timeout=0.1)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.results["a"], "done")
        self.assertEqual(r.attempts["a"], 2)

    def test_propagation_skip_transitive(self):
        dag = DAG()
        dag.add_task("a", lambda d: (_ for _ in ()).throw(ValueError("x")))
        dag.add_task("b", lambda d: 1, deps=["a"])
        dag.add_task("c", lambda d: 1, deps=["b"])
        dag.add_task("d", lambda d: 1, deps=["c"])
        r = dag.run()
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.status["b"], "skipped")
        self.assertEqual(r.status["c"], "skipped")
        self.assertEqual(r.status["d"], "skipped")
        self.assertEqual(r.attempts["b"], 0)
        self.assertEqual(r.attempts["c"], 0)
        self.assertEqual(r.attempts["d"], 0)
        self.assertFalse(r.ok)

    def test_fail_fast_cancels_independent(self):
        dag = DAG()
        dag.add_task("bad", lambda d: 1 / 0)
        dag.add_task("indep", lambda d: 42)
        r = dag.run(max_workers=1, fail_fast=True)
        self.assertEqual(r.status["bad"], "failed")
        self.assertEqual(r.status["indep"], "cancelled")
        self.assertEqual(r.attempts["indep"], 0)
        self.assertNotIn("indep", r.order)

    def test_fail_fast_waits_for_running(self):
        done = threading.Event()
        started = threading.Event()

        def slow_ok(_):
            started.set()
            done.wait(2)
            return "finished"

        def boom(_):
            started.wait(2)
            raise ValueError("boom")

        dag = DAG()
        dag.add_task("slow", slow_ok)
        dag.add_task("bad", boom)
        r = dag.run(max_workers=2, fail_fast=True)
        done.set()
        self.assertEqual(r.status["slow"], "success")
        self.assertEqual(r.results["slow"], "finished")
        self.assertEqual(r.status["bad"], "failed")

    def test_no_fail_fast_continues_independent(self):
        dag = DAG()
        dag.add_task("bad", lambda d: 1 / 0)
        dag.add_task("indep", lambda d: 42)
        dag.add_task("child", lambda d: "skip me", deps=["bad"])
        r = dag.run(fail_fast=False)
        self.assertEqual(r.status["bad"], "failed")
        self.assertEqual(r.status["indep"], "success")
        self.assertEqual(r.results["indep"], 42)
        self.assertEqual(r.status["child"], "skipped")

    def test_rerun_is_independent(self):
        calls = []

        def flaky(_):
            calls.append(1)
            if len(calls) % 2 == 1:
                raise RuntimeError("odd")
            return "even"

        dag = DAG()
        dag.add_task("a", flaky)
        r1 = dag.run()
        r2 = dag.run()
        self.assertEqual(r1.status["a"], "failed")
        self.assertEqual(r2.status["a"], "success")
        self.assertIsNone(r2.errors.get("a"))
        self.assertEqual(r1.attempts["a"], 1)
        self.assertEqual(r2.attempts["a"], 1)

    def test_order_is_start_order(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("b", lambda d: 1)
        dag.add_task("c", lambda d: 1, deps=["a"])
        r = dag.run(max_workers=1)
        self.assertEqual(r.order, ["a", "b", "c"])
        self.assertEqual(r.attempts, {"a": 1, "b": 1, "c": 1})

    def test_max_workers_respected(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def task(_):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return None

        dag = DAG()
        for i in range(8):
            dag.add_task(f"t{i}", task)
        r = dag.run(max_workers=3)
        self.assertTrue(r.ok)
        self.assertLessEqual(peak, 3)

    def test_single_worker_with_failures_no_deadlock(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1 / 0)
        dag.add_task("b", lambda d: 1, deps=["a"])
        dag.add_task("c", lambda d: 1)
        r = dag.run(max_workers=1)
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.status["b"], "skipped")
        self.assertIn(r.status["c"], ("cancelled", "success"))
        self.assertTrue(set(r.status) == {"a", "b", "c"})

    def test_diamond(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("b", lambda d: d["a"] + 1, deps=["a"])
        dag.add_task("c", lambda d: d["a"] * 10, deps=["a"])
        dag.add_task("d", lambda d: d["b"] + d["c"], deps=["b", "c"])
        r = dag.run(max_workers=4)
        self.assertTrue(r.ok)
        self.assertEqual(r.results["d"], 12)

    def test_many_tasks_stress(self):
        dag = DAG()
        for i in range(50):
            deps = [str(i - 1)] if i > 0 else []
            dag.add_task(str(i), lambda d, i=i: i, deps=deps)
        for i in range(50, 100):
            dag.add_task(f"x{i}", lambda d, i=i: i * 2)
        r = dag.run(max_workers=8)
        self.assertTrue(r.ok)
        self.assertEqual(len(r.order), 100)
        self.assertEqual(r.results["49"], 49)
        self.assertEqual(r.results["x99"], 198)


if __name__ == "__main__":
    unittest.main()
