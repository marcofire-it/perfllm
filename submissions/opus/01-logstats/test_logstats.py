#!/usr/bin/env python3
"""Test per logstats.py."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), 'logstats.py')


def run_logstats(log_content, extra_args=None):
    """Scrive il log in un file temporaneo, esegue logstats e restituisce (exit_code, stdout, stderr)."""
    with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(log_content)
        tmp = f.name
    try:
        cmd = [sys.executable, SCRIPT, tmp] + (extra_args or [])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        os.unlink(tmp)


class TestBasic(unittest.TestCase):

    def test_example_main(self):
        log = (
            "2024-03-01T12:34:56Z INFO auth Login ok user=42 latency_ms=120\n"
            "2024-03-01T12:35:01+02:00 ERROR payments Charge failed order=9 latency_ms=850\n"
            "2024-03-01T12:35:02Z WARN auth Token near expiry user=42\n"
        )
        rc, out, err = run_logstats(log)
        self.assertEqual(rc, 0)
        result = json.loads(out)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['malformed'], 0)
        self.assertEqual(result['by_level'], {'ERROR': 1, 'INFO': 1, 'WARN': 1})
        self.assertEqual(result['by_service'], {
            'auth': {'count': 2, 'errors': 0},
            'payments': {'count': 1, 'errors': 1},
        })
        self.assertEqual(result['latency_ms']['count'], 2)
        self.assertEqual(result['latency_ms']['min'], 120)
        self.assertEqual(result['latency_ms']['max'], 850)
        self.assertAlmostEqual(result['latency_ms']['avg'], 485.0)
        self.assertEqual(result['latency_ms']['p95'], 850)
        self.assertEqual(len(result['top_messages']), 3)
        self.assertEqual(result['first_timestamp'], '2024-03-01T10:35:01Z')
        self.assertEqual(result['last_timestamp'], '2024-03-01T12:35:02Z')

    def test_edge_case(self):
        log = (
            "2024-01-01T00:00:00Z INFO web GET /  latency_ms=10\n"
            "\n"
            "questa riga è rotta\n"
            "2024-01-01T00:00:00Z FATAL web boom\n"
            "2023-12-31T23:00:00-02:00 ERROR web GET /  latency_ms=abc\n"
        )
        rc, out, err = run_logstats(log)
        self.assertEqual(rc, 0)
        result = json.loads(out)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['malformed'], 2)
        self.assertEqual(result['by_level'], {'ERROR': 1, 'INFO': 1})
        self.assertEqual(result['by_service'], {'web': {'count': 2, 'errors': 1}})
        self.assertEqual(result['latency_ms'], {'count': 1, 'min': 10, 'max': 10, 'avg': 10.0, 'p95': 10})
        self.assertEqual(result['top_messages'], [{'message': 'GET /', 'count': 2}])
        self.assertEqual(result['first_timestamp'], '2024-01-01T00:00:00Z')
        self.assertEqual(result['last_timestamp'], '2024-01-01T01:00:00Z')


class TestFilters(unittest.TestCase):

    LOG = (
        "2024-01-01T00:00:00Z INFO svc1 msg1\n"
        "2024-01-02T00:00:00Z ERROR svc1 msg2\n"
        "2024-01-03T00:00:00Z WARN svc2 msg3\n"
        "bad line\n"
    )

    def test_level_filter(self):
        rc, out, _ = run_logstats(self.LOG, ['--level', 'ERROR'])
        self.assertEqual(rc, 0)
        result = json.loads(out)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['malformed'], 1)  # malformed always counted
        self.assertEqual(result['by_level'], {'ERROR': 1})

    def test_since_filter(self):
        rc, out, _ = run_logstats(self.LOG, ['--since', '2024-01-02T00:00:00Z'])
        result = json.loads(out)
        self.assertEqual(result['total'], 2)  # ERROR + WARN

    def test_until_filter(self):
        rc, out, _ = run_logstats(self.LOG, ['--until', '2024-01-01T00:00:00Z'])
        result = json.loads(out)
        self.assertEqual(result['total'], 1)

    def test_since_until_combined(self):
        rc, out, _ = run_logstats(self.LOG, [
            '--since', '2024-01-02T00:00:00Z',
            '--until', '2024-01-02T00:00:00Z',
        ])
        result = json.loads(out)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['by_level'], {'ERROR': 1})

    def test_top_zero(self):
        rc, out, _ = run_logstats(self.LOG, ['--top', '0'])
        result = json.loads(out)
        self.assertEqual(result['top_messages'], [])


class TestErrorCodes(unittest.TestCase):

    def test_file_not_found(self):
        cmd = [sys.executable, SCRIPT, '/no/such/file.log']
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, '')
        self.assertNotEqual(proc.stderr, '')

    def test_invalid_level(self):
        rc, out, err = run_logstats('', ['--level', 'FOO'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')

    def test_negative_top(self):
        rc, out, err = run_logstats('', ['--top', '-1'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')

    def test_invalid_since(self):
        rc, out, err = run_logstats('', ['--since', 'nope'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')


class TestEmptyAndEdge(unittest.TestCase):

    def test_empty_file(self):
        rc, out, _ = run_logstats('')
        result = json.loads(out)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['malformed'], 0)
        self.assertEqual(result['by_level'], {})
        self.assertEqual(result['by_service'], {})
        self.assertIsNone(result['latency_ms'])
        self.assertEqual(result['top_messages'], [])
        self.assertIsNone(result['first_timestamp'])
        self.assertIsNone(result['last_timestamp'])

    def test_only_blank_lines(self):
        rc, out, _ = run_logstats("   \n\n  \t  \n")
        result = json.loads(out)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['malformed'], 0)

    def test_all_malformed(self):
        rc, out, _ = run_logstats("bad1\nbad2\n")
        result = json.loads(out)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['malformed'], 2)

    def test_message_only_kv(self):
        """Template vuoto quando il messaggio è solo k=v."""
        log = "2024-01-01T00:00:00Z INFO svc key=val\n"
        rc, out, _ = run_logstats(log)
        result = json.loads(out)
        self.assertEqual(result['top_messages'], [{'message': '', 'count': 1}])

    def test_negative_offset(self):
        log = "2024-06-15T10:00:00-05:00 DEBUG svc hello\n"
        rc, out, _ = run_logstats(log)
        result = json.loads(out)
        self.assertEqual(result['first_timestamp'], '2024-06-15T15:00:00Z')

    def test_p95_single_value(self):
        log = "2024-01-01T00:00:00Z INFO svc msg latency_ms=42\n"
        rc, out, _ = run_logstats(log)
        result = json.loads(out)
        self.assertEqual(result['latency_ms']['p95'], 42)

    def test_p95_multiple_values(self):
        """20 valori: p95 = ceil(0.95*20) = 19-esimo (1-based)."""
        lines = []
        for i in range(1, 21):
            lines.append(f"2024-01-01T00:00:{i:02d}Z INFO svc msg latency_ms={i * 10}\n")
        log = ''.join(lines)
        rc, out, _ = run_logstats(log)
        result = json.loads(out)
        # Sorted: 10,20,...,200. 19th element (1-based) = 190
        self.assertEqual(result['latency_ms']['p95'], 190)
        self.assertEqual(result['latency_ms']['count'], 20)
        self.assertEqual(result['latency_ms']['min'], 10)
        self.assertEqual(result['latency_ms']['max'], 200)


class TestTopMessages(unittest.TestCase):

    def test_ordering(self):
        """count desc, poi message asc."""
        log = (
            "2024-01-01T00:00:00Z INFO svc beta\n"
            "2024-01-01T00:00:01Z INFO svc alpha\n"
            "2024-01-01T00:00:02Z INFO svc beta\n"
            "2024-01-01T00:00:03Z INFO svc gamma\n"
        )
        rc, out, _ = run_logstats(log, ['--top', '5'])
        result = json.loads(out)
        self.assertEqual(result['top_messages'], [
            {'message': 'beta', 'count': 2},
            {'message': 'alpha', 'count': 1},
            {'message': 'gamma', 'count': 1},
        ])

    def test_kv_removal(self):
        """Multiple k=v rimossi, spazi compattati."""
        log = "2024-01-01T00:00:00Z INFO svc hello k1=v1 world k2=v2\n"
        rc, out, _ = run_logstats(log)
        result = json.loads(out)
        self.assertEqual(result['top_messages'][0]['message'], 'hello world')


if __name__ == '__main__':
    unittest.main()
