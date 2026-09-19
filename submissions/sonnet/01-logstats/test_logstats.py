"""Test per logstats.py (unittest, sola libreria standard)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logstats.py")


def run(args, content=None):
    tmp_path = None
    full_args = list(args)
    if content is not None:
        fd, tmp_path = tempfile.mkstemp(suffix=".log", dir=os.path.dirname(os.path.abspath(__file__)))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        full_args = [tmp_path] + list(args)
    try:
        proc = subprocess.run(
            [sys.executable, SCRIPT] + full_args,
            capture_output=True,
            text=True,
        )
        return proc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


class TestLogstats(unittest.TestCase):
    def test_example_from_task(self):
        content = (
            "2024-03-01T12:34:56Z INFO auth Login ok user=42 latency_ms=120\n"
            "2024-03-01T12:35:01+02:00 ERROR payments Charge failed order=9 latency_ms=850\n"
            "2024-03-01T12:35:02Z WARN auth Token near expiry user=42\n"
        )
        proc = run([], content)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["malformed"], 0)
        self.assertEqual(data["by_level"], {"ERROR": 1, "INFO": 1, "WARN": 1})
        self.assertEqual(
            data["by_service"],
            {"auth": {"count": 2, "errors": 0}, "payments": {"count": 1, "errors": 1}},
        )
        self.assertEqual(
            data["latency_ms"],
            {"count": 2, "min": 120, "max": 850, "avg": 485.0, "p95": 850},
        )
        self.assertEqual(data["first_timestamp"], "2024-03-01T10:35:01Z")
        self.assertEqual(data["last_timestamp"], "2024-03-01T12:35:02Z")

    def test_edge_case_from_task(self):
        content = (
            "2024-01-01T00:00:00Z INFO web GET /  latency_ms=10\n"
            "\n"
            "questa riga è rotta\n"
            "2024-01-01T00:00:00Z FATAL web boom\n"
            "2023-12-31T23:00:00-02:00 ERROR web GET /  latency_ms=abc\n"
        )
        proc = run([], content)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["malformed"], 2)
        self.assertEqual(data["by_level"], {"ERROR": 1, "INFO": 1})
        self.assertEqual(data["by_service"], {"web": {"count": 2, "errors": 1}})
        self.assertEqual(
            data["latency_ms"], {"count": 1, "min": 10, "max": 10, "avg": 10.0, "p95": 10}
        )
        self.assertEqual(data["top_messages"], [{"message": "GET /", "count": 2}])
        self.assertEqual(data["first_timestamp"], "2024-01-01T00:00:00Z")
        self.assertEqual(data["last_timestamp"], "2024-01-01T01:00:00Z")

    def test_file_not_found(self):
        proc = run(["/percorso/inesistente.log"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertTrue(proc.stderr.strip() != "")

    def test_invalid_top(self):
        proc = run(["--top", "-1"], "2024-01-01T00:00:00Z INFO web hello\n")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_invalid_level(self):
        proc = run(["--level", "FOO"], "2024-01-01T00:00:00Z INFO web hello\n")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_invalid_since(self):
        proc = run(["--since", "not-a-date"], "2024-01-01T00:00:00Z INFO web hello\n")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_empty_total(self):
        content = "solo una riga rotta senza timestamp valido\n"
        proc = run([], content)
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["malformed"], 1)
        self.assertIsNone(data["first_timestamp"])
        self.assertIsNone(data["last_timestamp"])
        self.assertIsNone(data["latency_ms"])
        self.assertEqual(data["top_messages"], [])

    def test_level_filter(self):
        content = (
            "2024-01-01T00:00:00Z INFO web a\n"
            "2024-01-01T00:00:01Z ERROR web b\n"
        )
        proc = run(["--level", "ERROR"], content)
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["by_level"], {"ERROR": 1})

    def test_since_until_inclusive(self):
        content = (
            "2024-01-01T00:00:00Z INFO web a\n"
            "2024-01-01T00:00:01Z INFO web b\n"
            "2024-01-01T00:00:02Z INFO web c\n"
        )
        proc = run(
            ["--since", "2024-01-01T00:00:00Z", "--until", "2024-01-01T00:00:01Z"],
            content,
        )
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 2)

    def test_top_messages_ordering(self):
        content = (
            "2024-01-01T00:00:00Z INFO web zeta\n"
            "2024-01-01T00:00:01Z INFO web alpha\n"
            "2024-01-01T00:00:02Z INFO web alpha\n"
        )
        proc = run(["--top", "5"], content)
        data = json.loads(proc.stdout)
        self.assertEqual(
            data["top_messages"],
            [{"message": "alpha", "count": 2}, {"message": "zeta", "count": 1}],
        )

    def test_empty_template_message(self):
        content = "2024-01-01T00:00:00Z INFO web user=1 latency_ms=5\n"
        proc = run([], content)
        data = json.loads(proc.stdout)
        self.assertEqual(data["top_messages"], [{"message": "", "count": 1}])

    def test_blank_lines_ignored(self):
        content = "\n   \n2024-01-01T00:00:00Z INFO web hi\n\n"
        proc = run([], content)
        data = json.loads(proc.stdout)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["malformed"], 0)

    def test_p95_nearest_rank(self):
        lines = []
        for v in range(1, 21):  # 20 values 1..20
            lines.append(f"2024-01-01T00:00:{v:02d}Z INFO web m latency_ms={v}\n")
        proc = run([], "".join(lines))
        data = json.loads(proc.stdout)
        # ceil(0.95*20) = 19 -> valore ordinato in posizione 19 (1-based) = 19
        self.assertEqual(data["latency_ms"]["p95"], 19)


if __name__ == "__main__":
    unittest.main()
