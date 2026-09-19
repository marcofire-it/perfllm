import threading
import time
import unittest

from dagrunner import (
    DAG,
    CycleError,
    DuplicateTaskError,
    UnknownDependencyError,
)


class TestAddTaskValidation(unittest.TestCase):
    def test_duplicate_immediate(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        with self.assertRaises(DuplicateTaskError):
            dag.add_task("a", lambda d: 2)

    def test_empty_name(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("", lambda d: 1)

    def test_non_callable(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", "not callable")

    def test_negative_retries(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, retries=-1)

    def test_zero_timeout(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, timeout=0)

    def test_negative_timeout(self):
        dag = DAG()
        with self.assertRaises(ValueError):
            dag.add_task("a", lambda d: 1, timeout=-5)

    def test_deps_can_reference_future_task(self):
        dag = DAG()
        # non deve sollevare finché non si chiama run()/topological_order()
        dag.add_task("a", lambda d: 1, deps=["b"])
        dag.add_task("b", lambda d: 2)
        r = dag.run()
        self.assertTrue(r.ok)


class TestTopologicalOrder(unittest.TestCase):
    def test_unknown_dependency(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["missing"])
        with self.assertRaises(UnknownDependencyError):
            dag.topological_order()

    def test_cycle(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["b"])
        dag.add_task("b", lambda d: 1, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()

    def test_self_loop(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1, deps=["a"])
        with self.assertRaises(CycleError):
            dag.topological_order()

    def test_deterministic_order(self):
        dag = DAG()
        dag.add_task("c", lambda d: None)
        dag.add_task("b", lambda d: None)
        dag.add_task("a", lambda d: None)
        # nessuna dipendenza: ordine = ordine di inserimento
        self.assertEqual(dag.topological_order(), ["c", "b", "a"])

    def test_does_not_execute(self):
        calls = []
        dag = DAG()
        dag.add_task("a", lambda d: calls.append("a"))
        dag.topological_order()
        self.assertEqual(calls, [])


class TestExampleFromSpec(unittest.TestCase):
    def test_example(self):
        dag = DAG()
        dag.add_task("fetch", lambda d: [1, 2, 3])
        dag.add_task("double", lambda d: [x * 2 for x in d["fetch"]], deps=["fetch"])
        dag.add_task("sum", lambda d: sum(d["double"]), deps=["double"])
        dag.add_task("log", lambda d: len(d["fetch"]), deps=["fetch"])

        r = dag.run(max_workers=2)
        self.assertTrue(r.ok)
        self.assertEqual(r.results["sum"], 12)
        self.assertEqual(r.order[0], "fetch")
        self.assertEqual(set(r.order[1:3]), {"double", "log"})


class TestRunBasics(unittest.TestCase):
    def test_empty_dag(self):
        dag = DAG()
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.status, {})
        self.assertEqual(r.results, {})
        self.assertEqual(r.errors, {})
        self.assertEqual(r.order, [])
        self.assertEqual(r.attempts, {})

    def test_max_workers_invalid(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        with self.assertRaises(ValueError):
            dag.run(max_workers=0)

    def test_invalid_graph_no_execution(self):
        calls = []
        dag = DAG()
        dag.add_task("a", lambda d: calls.append("a"), deps=["b"])
        dag.add_task("b", lambda d: calls.append("b"), deps=["a"])
        with self.assertRaises(CycleError):
            dag.run()
        self.assertEqual(calls, [])

    def test_deps_dict_contains_only_direct_deps(self):
        seen = {}

        def rec(d):
            seen["a"] = dict(d)
            return "ra"

        dag = DAG()
        dag.add_task("x", lambda d: "rx")
        dag.add_task("y", lambda d: "ry")
        dag.add_task("a", rec, deps=["x", "y"])
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(seen["a"], {"x": "rx", "y": "ry"})

    def test_rerunnable(self):
        dag = DAG()
        counter = {"n": 0}

        def fn(d):
            counter["n"] += 1
            return counter["n"]

        dag.add_task("a", fn)
        r1 = dag.run()
        r2 = dag.run()
        self.assertNotEqual(r1.results["a"], r2.results["a"])


class TestMaxWorkers(unittest.TestCase):
    def test_never_exceeds_max_workers(self):
        lock = threading.Lock()
        current = {"n": 0, "max": 0}

        def fn(d):
            with lock:
                current["n"] += 1
                current["max"] = max(current["max"], current["n"])
            time.sleep(0.05)
            with lock:
                current["n"] -= 1
            return 1

        dag = DAG()
        for i in range(10):
            dag.add_task(f"t{i}", fn)
        r = dag.run(max_workers=3)
        self.assertTrue(r.ok)
        self.assertLessEqual(current["max"], 3)


class TestRetries(unittest.TestCase):
    def test_retries_eventually_succeed(self):
        state = {"n": 0}

        def fn(d):
            state["n"] += 1
            if state["n"] < 3:
                raise RuntimeError("boom")
            return "ok"

        dag = DAG()
        dag.add_task("a", fn, retries=5)
        r = dag.run()
        self.assertTrue(r.ok)
        self.assertEqual(r.attempts["a"], 3)

    def test_retries_exhausted(self):
        def fn(d):
            raise RuntimeError("always fails")

        dag = DAG()
        dag.add_task("a", fn, retries=2)
        r = dag.run()
        self.assertEqual(r.status["a"], "failed")
        self.assertEqual(r.attempts["a"], 3)
        self.assertIsInstance(r.errors["a"], RuntimeError)


class TestTimeout(unittest.TestCase):
    def test_timeout_treated_as_failure(self):
        def fn(d):
            time.sleep(1.0)
            return "late"

        dag = DAG()
        dag.add_task("a", fn, timeout=0.1)
        start = time.monotonic()
        r = dag.run()
        elapsed = time.monotonic() - start
        self.assertEqual(r.status["a"], "failed")
        self.assertIsInstance(r.errors["a"], TimeoutError)
        self.assertLess(elapsed, 0.9)  # run() non aspetta il completamento

    def test_timeout_result_ignored(self):
        def fn(d):
            time.sleep(0.2)
            return "late-value"

        dag = DAG()
        dag.add_task("a", fn, timeout=0.05, retries=1)
        r = dag.run()
        self.assertEqual(r.status["a"], "failed")


class TestPropagationAndFailFast(unittest.TestCase):
    def build_diamond_with_failure(self):
        dag = DAG()

        def boom(d):
            raise ValueError("fail")

        dag.add_task("root", boom)
        dag.add_task("dep_a", lambda d: "a", deps=["root"])
        dag.add_task("dep_b", lambda d: "b", deps=["dep_a"])
        dag.add_task("independent", lambda d: "i")
        return dag

    def test_fail_fast_true(self):
        dag = self.build_diamond_with_failure()
        r = dag.run(max_workers=4, fail_fast=True)
        self.assertEqual(r.status["root"], "failed")
        self.assertEqual(r.status["dep_a"], "skipped")
        self.assertEqual(r.status["dep_b"], "skipped")
        self.assertEqual(r.attempts["dep_a"], 0)
        self.assertEqual(r.attempts["dep_b"], 0)
        self.assertIn(r.status["independent"], {"cancelled", "success"})
        self.assertFalse(r.ok)

    def test_fail_fast_false_independent_runs(self):
        dag = self.build_diamond_with_failure()
        r = dag.run(max_workers=4, fail_fast=False)
        self.assertEqual(r.status["root"], "failed")
        self.assertEqual(r.status["dep_a"], "skipped")
        self.assertEqual(r.status["dep_b"], "skipped")
        self.assertEqual(r.status["independent"], "success")
        self.assertFalse(r.ok)

    def test_fail_fast_serializes_cancels_not_started(self):
        # con max_workers=1 il task indipendente non fa in tempo a partire
        dag = DAG()

        def boom(d):
            raise ValueError("fail")

        dag.add_task("root", boom)
        dag.add_task("child", lambda d: 1, deps=["root"])
        dag.add_task("other1", lambda d: 1)
        dag.add_task("other2", lambda d: 1)

        r = dag.run(max_workers=1, fail_fast=True)
        self.assertEqual(r.status["root"], "failed")
        self.assertEqual(r.status["child"], "skipped")
        # other1/other2 dipendono da nessuno -> cancelled (non avviati)
        for n in ("other1", "other2"):
            self.assertIn(r.status[n], {"cancelled"})
            self.assertEqual(r.attempts[n], 0)


class TestOrderingAndStartOrder(unittest.TestCase):
    def test_order_records_start_order(self):
        dag = DAG()
        dag.add_task("a", lambda d: 1)
        dag.add_task("b", lambda d: 1, deps=["a"])
        dag.add_task("c", lambda d: 1, deps=["a"])
        r = dag.run(max_workers=4)
        self.assertEqual(r.order[0], "a")
        self.assertEqual(set(r.order[1:]), {"b", "c"})
        self.assertEqual(len(r.order), 3)


if __name__ == "__main__":
    unittest.main()
