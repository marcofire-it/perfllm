"""Tests for logstats.py (run with: python -m unittest or pytest)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "logstats.py")
PYTHON = sys.executable


def run(args):
    return subprocess.run([PYTHON, SCRIPT] + args, capture_output=True, text=True)


class LogStatsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "test.log")

    def write_log(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return self.path

    def stats(self, *args):
        proc = run(list(args))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotEqual(proc.stdout, "", "nothing printed on stdout")
        return json.loads(proc.stdout)

    def test_spec_example(self):
        self.write_log(
            "2024-03-01T12:34:56Z INFO auth Login ok user=42 latency_ms=120\n"
            "2024-03-01T12:35:01+02:00 ERROR payments Charge failed order=9 latency_ms=850\n"
            "2024-03-01T12:35:02Z WARN auth Token near expiry user=42\n"
        )
        out = self.stats(self.path)
        self.assertEqual(out["total"], 3)
        self.assertEqual(out["malformed"], 0)
        self.assertEqual(out["by_level"], {"ERROR": 1, "INFO": 1, "WARN": 1})
        self.assertEqual(out["by_service"], {
            "auth": {"count": 2, "errors": 0},
            "payments": {"count": 1, "errors": 1},
        })
        self.assertEqual(out["latency_ms"],
                         {"count": 2, "min": 120, "max": 850, "avg": 485.0, "p95": 850})
        self.assertEqual(out["top_messages"], [
            {"message": "Charge failed", "count": 1},
            {"message": "Login ok", "count": 1},
            {"message": "Token near expiry", "count": 1},
        ])
        self.assertEqual(out["first_timestamp"], "2024-03-01T10:35:01Z")
        self.assertEqual(out["last_timestamp"], "2024-03-01T12:35:02Z")

    def test_spec_edge_case(self):
        self.write_log(
            "2024-01-01T00:00:00Z INFO web GET /  latency_ms=10\n"
            "\n"
            "questa riga è rotta\n"
            "2024-01-01T00:00:00Z FATAL web boom\n"
            "2023-12-31T23:00:00-02:00 ERROR web GET /  latency_ms=abc\n"
        )
        out = self.stats(self.path)
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["malformed"], 2)
        self.assertEqual(out["by_level"], {"ERROR": 1, "INFO": 1})
        self.assertEqual(out["by_service"], {"web": {"count": 2, "errors": 1}})
        self.assertEqual(out["latency_ms"],
                         {"count": 1, "min": 10, "max": 10, "avg": 10.0, "p95": 10})
        self.assertEqual(out["top_messages"], [{"message": "GET /", "count": 2}])
        self.assertEqual(out["first_timestamp"], "2024-01-01T00:00:00Z")
        self.assertEqual(out["last_timestamp"], "2024-01-01T01:00:00Z")

    def test_whitespace_and_empty(self):
        self.write_log(
            "   2024-01-01T00:00:00Z INFO web hello world   \n"
            "   \n"
            "2024-01-01T00:00:01Z DEBUG web a b\n"
        )
        out = self.stats(self.path)
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["malformed"], 0)
        self.assertEqual(out["top_messages"], [
            {"message": "a b", "count": 1},
            {"message": "hello world", "count": 1},
        ])

    def test_malformed_variants(self):
        self.write_log(
            "2024-01-01T00:00:00Z INFO web ok\n"
            "2024-01-01T00:00:00Z INFO web\n"                    # missing message
            "not-a-timestamp INFO web ok\n"                      # bad timestamp
            "2024-13-01T00:00:00Z INFO web ok\n"                 # invalid month
            "2024-01-01T00:00:00 INFO web ok\n"                  # no timezone
            "2024-01-01T00:00:00Z info web ok\n"                 # lowercase level
            "2024-01-01T00:00:00Z FATAL web ok\n"                # unknown level
        )
        out = self.stats(self.path)
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["malformed"], 6)

    def test_since_until_inclusive_utc(self):
        self.write_log(
            "2024-01-01T10:00:00+02:00 INFO web a\n"   # 08:00 UTC
            "2024-01-01T09:00:00Z INFO web b\n"        # 09:00 UTC
            "2024-01-01T11:00:00Z INFO web c\n"        # 11:00 UTC
            "2024-01-01T12:00:00Z INFO web d\n"        # 12:00 UTC
        )
        out = self.stats(self.path, "--since", "2024-01-01T09:00:00Z",
                         "--until", "2024-01-01T11:00:00Z")
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["first_timestamp"], "2024-01-01T09:00:00Z")
        self.assertEqual(out["last_timestamp"], "2024-01-01T11:00:00Z")
        self.assertEqual(out["top_messages"], [
            {"message": "b", "count": 1},
            {"message": "c", "count": 1},
        ])

    def test_level_filter(self):
        self.write_log(
            "2024-01-01T00:00:00Z INFO web a\n"
            "2024-01-01T00:00:01Z ERROR web b\n"
            "2024-01-01T00:00:02Z ERROR db c\n"
        )
        out = self.stats(self.path, "--level", "ERROR")
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["by_level"], {"ERROR": 2})
        self.assertEqual(out["by_service"], {
            "db": {"count": 1, "errors": 1},
            "web": {"count": 1, "errors": 1},
        })

    def test_top(self):
        self.write_log(
            "2024-01-01T00:00:00Z INFO web zed\n"
            "2024-01-01T00:00:01Z INFO web zed\n"
            "2024-01-01T00:00:02Z INFO web alpha\n"
            "2024-01-01T00:00:03Z INFO web alpha\n"
            "2024-01-01T00:00:04Z INFO web alpha\n"
            "2024-01-01T00:00:05Z INFO web beta\n"
        )
        out = self.stats(self.path, "--top", "2")
        self.assertEqual(out["top_messages"], [
            {"message": "alpha", "count": 3},
            {"message": "zed", "count": 2},
        ])
        out = self.stats(self.path, "--top", "0")
        self.assertEqual(out["top_messages"], [])

    def test_empty_template_included(self):
        self.write_log("2024-01-01T00:00:00Z INFO web user=1 order=2\n")
        out = self.stats(self.path)
        self.assertEqual(out["top_messages"], [{"message": "", "count": 1}])

    def test_latency_null_when_absent(self):
        self.write_log("2024-01-01T00:00:00Z INFO web no latency here\n")
        out = self.stats(self.path)
        self.assertIsNone(out["latency_ms"])

    def test_p95_nearest_rank(self):
        lines = "".join(
            f"2024-01-01T00:00:00Z INFO web job latency_ms={i}\n"
            for i in range(1, 21)  # 20 values -> p95 rank ceil(19) = 19 -> value 19
        )
        self.write_log(lines)
        out = self.stats(self.path)
        self.assertEqual(out["latency_ms"]["p95"], 19)
        self.assertEqual(out["latency_ms"]["min"], 1)
        self.assertEqual(out["latency_ms"]["max"], 20)
        self.assertEqual(out["latency_ms"]["avg"], 10.5)

    def test_single_line_empty_result(self):
        self.write_log("2024-01-01T00:00:00Z FATAL web broken\n")
        out = self.stats(self.path)
        self.assertEqual(out["total"], 0)
        self.assertEqual(out["malformed"], 1)
        self.assertEqual(out["by_level"], {})
        self.assertEqual(out["by_service"], {})
        self.assertIsNone(out["latency_ms"])
        self.assertEqual(out["top_messages"], [])
        self.assertIsNone(out["first_timestamp"])
        self.assertIsNone(out["last_timestamp"])

    def test_unsorted_timestamps(self):
        self.write_log(
            "2024-01-01T12:00:00Z INFO web late\n"
            "2024-01-01T03:00:00Z INFO web early\n"
        )
        out = self.stats(self.path)
        self.assertEqual(out["first_timestamp"], "2024-01-01T03:00:00Z")
        self.assertEqual(out["last_timestamp"], "2024-01-01T12:00:00Z")

    def test_missing_file_exit_2(self):
        proc = run([os.path.join(self._tmp.name, "nope.log")])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertNotEqual(proc.stderr, "")

    def test_invalid_args_exit_1(self):
        self.write_log("2024-01-01T00:00:00Z INFO web ok\n")
        for args in (
            [self.path, "--top", "-1"],
            [self.path, "--top", "abc"],
            [self.path, "--level", "FOO"],
            [self.path, "--since", "yesterday"],
            [self.path, "--until", "2024-01-01T00:00:00"],  # missing timezone
            [self.path, "--bogus", "x"],
            [self.path, "--top"],                            # missing value
            [],
            [self.path, "extra.log"],
        ):
            proc = run(args)
            self.assertEqual(proc.returncode, 1, f"args={args}, stderr={proc.stderr}")
            self.assertEqual(proc.stdout, "")
            self.assertNotEqual(proc.stderr, "")


if __name__ == "__main__":
    unittest.main()
