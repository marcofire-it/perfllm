"""Test nascosti per il task 01 (logstats)."""
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_KEYS = {
    "total", "malformed", "by_level", "by_service", "latency_ms",
    "top_messages", "first_timestamp", "last_timestamp",
}


def run_cli(submission_dir, *args, timeout=60):
    return subprocess.run(
        [sys.executable, str(submission_dir / "logstats.py"), *[str(a) for a in args]],
        capture_output=True, text=True, timeout=timeout,
    )


def run_json(submission_dir, *args, timeout=60):
    p = run_cli(submission_dir, *args, timeout=timeout)
    assert p.returncode == 0, f"exit={p.returncode} stderr={p.stderr[:500]}"
    return json.loads(p.stdout)


def write_log(tmp_path, name, text):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


# ----------------------------------------------------------------- core


@pytest.mark.core
def test_task_example(submission_dir):
    out = run_json(submission_dir, FIXTURES / "example.log")
    assert out == {
        "total": 3,
        "malformed": 0,
        "by_level": {"ERROR": 1, "INFO": 1, "WARN": 1},
        "by_service": {
            "auth": {"count": 2, "errors": 0},
            "payments": {"count": 1, "errors": 1},
        },
        "latency_ms": {"count": 2, "min": 120, "max": 850, "avg": 485.0, "p95": 850},
        "top_messages": [
            {"message": "Charge failed", "count": 1},
            {"message": "Login ok", "count": 1},
            {"message": "Token near expiry", "count": 1},
        ],
        "first_timestamp": "2024-03-01T10:35:01Z",
        "last_timestamp": "2024-03-01T12:35:02Z",
    }


@pytest.mark.core
def test_task_edge_example_exact(submission_dir):
    out = run_json(submission_dir, FIXTURES / "edge.log")
    assert out == {
        "total": 2,
        "malformed": 2,
        "by_level": {"ERROR": 1, "INFO": 1},
        "by_service": {"web": {"count": 2, "errors": 1}},
        "latency_ms": {"count": 1, "min": 10, "max": 10, "avg": 10.0, "p95": 10},
        "top_messages": [{"message": "GET /", "count": 2}],
        "first_timestamp": "2024-01-01T00:00:00Z",
        "last_timestamp": "2024-01-01T01:00:00Z",
    }


@pytest.mark.core
def test_output_is_single_json_with_exact_keys(submission_dir):
    p = run_cli(submission_dir, FIXTURES / "example.log")
    assert p.returncode == 0
    out = json.loads(p.stdout)  # deve essere UN solo oggetto JSON
    assert isinstance(out, dict)
    assert set(out.keys()) == EXPECTED_KEYS


@pytest.mark.core
def test_by_level_and_by_service_sorted_keys(submission_dir):
    out = run_json(submission_dir, FIXTURES / "mixed.log")
    assert list(out["by_level"].keys()) == ["DEBUG", "ERROR", "INFO", "WARN"]
    assert out["by_level"] == {"DEBUG": 1, "ERROR": 3, "INFO": 3, "WARN": 1}
    assert list(out["by_service"].keys()) == ["auth", "db", "web"]


@pytest.mark.core
def test_errors_per_service(submission_dir):
    out = run_json(submission_dir, FIXTURES / "mixed.log")
    assert out["by_service"] == {
        "auth": {"count": 3, "errors": 1},
        "db": {"count": 2, "errors": 1},
        "web": {"count": 3, "errors": 1},
    }


@pytest.mark.core
def test_latency_stats_basic(submission_dir):
    # mixed.log: 100, 50, 900, 400 (latency_ms=-5 non è un intero non negativo -> ignorato)
    out = run_json(submission_dir, FIXTURES / "mixed.log")
    assert out["latency_ms"] == {"count": 4, "min": 50, "max": 900, "avg": 362.5, "p95": 900}
    assert out["total"] == 8


@pytest.mark.core
def test_latency_avg_two_decimals(submission_dir, tmp_path):
    lines = [f"2024-01-01T00:00:0{i}Z INFO s m latency_ms={v}" for i, v in enumerate([1, 2, 2])]
    f = write_log(tmp_path, "a.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["latency_ms"]["avg"] == 1.67
    assert isinstance(out["latency_ms"]["avg"], float)


@pytest.mark.core
def test_latency_p95_nearest_rank_unsorted_20(submission_dir, tmp_path):
    vals = list(range(10, 210, 10))  # 10..200, n=20 -> ceil(19)=19-esimo -> 190
    random.Random(7).shuffle(vals)
    lines = [f"2024-01-01T00:00:00Z INFO s req latency_ms={v}" for v in vals]
    f = write_log(tmp_path, "p.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["latency_ms"]["p95"] == 190
    assert out["latency_ms"]["min"] == 10
    assert out["latency_ms"]["max"] == 200
    assert out["latency_ms"]["avg"] == 105.0


@pytest.mark.core
def test_latency_p95_small_n(submission_dir, tmp_path):
    # n=3 -> ceil(2.85)=3 -> il massimo; n=1 -> l'unico valore
    f3 = write_log(tmp_path, "3.log", "\n".join(
        f"2024-01-01T00:00:00Z INFO s x latency_ms={v}" for v in [30, 10, 20]) + "\n")
    assert run_json(submission_dir, f3)["latency_ms"]["p95"] == 30
    f1 = write_log(tmp_path, "1.log", "2024-01-01T00:00:00Z INFO s x latency_ms=7\n")
    out = run_json(submission_dir, f1)
    assert out["latency_ms"] == {"count": 1, "min": 7, "max": 7, "avg": 7.0, "p95": 7}


@pytest.mark.core
def test_latency_null_when_absent(submission_dir, tmp_path):
    f = write_log(tmp_path, "n.log", "2024-01-01T00:00:00Z INFO s no latency here\n")
    assert run_json(submission_dir, f)["latency_ms"] is None


@pytest.mark.core
def test_top_messages_ordering_count_desc_then_message_asc(submission_dir, tmp_path):
    lines = (
        ["2024-01-01T00:00:00Z INFO s zeta"] * 2
        + ["2024-01-01T00:00:00Z INFO s alpha"] * 2
        + ["2024-01-01T00:00:00Z INFO s mid"] * 3
        + ["2024-01-01T00:00:00Z INFO s Beta"]
    )
    f = write_log(tmp_path, "t.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f, "--top", 10)
    assert out["top_messages"] == [
        {"message": "mid", "count": 3},
        {"message": "alpha", "count": 2},
        {"message": "zeta", "count": 2},
        {"message": "Beta", "count": 1},
    ]


@pytest.mark.core
def test_top_default_is_3(submission_dir, tmp_path):
    lines = [f"2024-01-01T00:00:00Z INFO s msg{i}" for i in range(6)]
    f = write_log(tmp_path, "d.log", "\n".join(lines) + "\n")
    assert len(run_json(submission_dir, f)["top_messages"]) == 3


@pytest.mark.core
def test_template_strips_kv_and_collapses_spaces(submission_dir, tmp_path):
    lines = [
        "2024-01-01T00:00:00Z INFO web GET   /home   user=1 latency_ms=5",
        "2024-01-01T00:00:01Z INFO web user=2 GET /home",
        "2024-01-01T00:00:02Z INFO web  GET /home  ",
    ]
    f = write_log(tmp_path, "k.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["top_messages"] == [{"message": "GET /home", "count": 3}]


@pytest.mark.core
def test_since_until_inclusive_utc_with_offsets(submission_dir, tmp_path):
    lines = [
        "2024-01-01T09:59:59Z INFO s before",
        "2024-01-01T12:00:00+02:00 INFO s start",   # 10:00:00Z
        "2024-01-01T11:00:00Z INFO s middle",
        "2024-01-01T10:00:00-02:00 INFO s end",     # 12:00:00Z
        "2024-01-01T12:00:01Z INFO s after",
    ]
    f = write_log(tmp_path, "r.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f, "--since", "2024-01-01T10:00:00Z",
                   "--until", "2024-01-01T13:00:00+01:00", "--top", 10)
    assert out["total"] == 3
    assert {m["message"] for m in out["top_messages"]} == {"start", "middle", "end"}
    assert out["first_timestamp"] == "2024-01-01T10:00:00Z"
    assert out["last_timestamp"] == "2024-01-01T12:00:00Z"


@pytest.mark.core
def test_level_filter(submission_dir):
    out = run_json(submission_dir, FIXTURES / "mixed.log", "--level", "ERROR")
    assert out["total"] == 3
    assert out["by_level"] == {"ERROR": 3}
    assert out["by_service"] == {
        "auth": {"count": 1, "errors": 1},
        "db": {"count": 1, "errors": 1},
        "web": {"count": 1, "errors": 1},
    }
    assert out["latency_ms"] == {"count": 1, "min": 900, "max": 900, "avg": 900.0, "p95": 900}


@pytest.mark.core
def test_first_last_timestamp_not_chronological(submission_dir):
    out = run_json(submission_dir, FIXTURES / "mixed.log")
    assert out["first_timestamp"] == "2024-06-01T06:00:00Z"  # 07:00+01:00
    assert out["last_timestamp"] == "2024-06-01T14:00:00Z"


@pytest.mark.core
def test_multiple_spaces_between_fields(submission_dir, tmp_path):
    f = write_log(tmp_path, "sp.log", "2024-01-01T00:00:00Z    WARN\t\tsvc   hello   world\n")
    out = run_json(submission_dir, f)
    assert out["total"] == 1
    assert out["by_service"] == {"svc": {"count": 1, "errors": 0}}
    assert out["top_messages"] == [{"message": "hello world", "count": 1}]


# ----------------------------------------------------------------- edge


@pytest.mark.edge
def test_malformed_variants(submission_dir, tmp_path):
    lines = [
        "2024-01-01T00:00:00Z INFO svc",                # manca il messaggio
        "2024-01-01T00:00:00Z INFO",                    # mancano service e message
        "2024-01-01T00:00:00Z FATAL svc x",             # livello sconosciuto
        "2024-01-01T00:00:00Z info svc x",              # livello minuscolo
        "2024-13-01T00:00:00Z INFO svc x",              # mese invalido
        "2024-01-01 00:00:00Z INFO svc x",              # spazio invece di T -> campi sballati
        "2024-01-01T00:00:00 INFO svc x",               # manca Z/offset
        "not-a-ts INFO svc x",
        "2024-01-01T00:00:00Z INFO svc ok",             # valida
    ]
    f = write_log(tmp_path, "m.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["total"] == 1
    assert out["malformed"] == 8


@pytest.mark.edge
def test_blank_and_whitespace_lines_ignored(submission_dir):
    out = run_json(submission_dir, FIXTURES / "blank_lines.log")
    assert out["total"] == 2
    assert out["malformed"] == 0


@pytest.mark.edge
def test_malformed_count_independent_of_filters(submission_dir, tmp_path):
    lines = [
        "garbage line here",
        "2024-01-01T00:00:00Z INFO svc a",
        "2024-01-02T00:00:00Z ERROR svc b",
    ]
    f = write_log(tmp_path, "mf.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f, "--level", "ERROR", "--since", "2024-01-02T00:00:00Z")
    assert out["malformed"] == 1
    assert out["total"] == 1


@pytest.mark.edge
def test_empty_result_nulls(submission_dir, tmp_path):
    f = write_log(tmp_path, "e.log", "2024-01-01T00:00:00Z INFO svc a\n")
    out = run_json(submission_dir, f, "--level", "ERROR")
    assert out == {
        "total": 0, "malformed": 0, "by_level": {}, "by_service": {},
        "latency_ms": None, "top_messages": [],
        "first_timestamp": None, "last_timestamp": None,
    }


@pytest.mark.edge
def test_empty_file(submission_dir, tmp_path):
    f = write_log(tmp_path, "empty.log", "")
    out = run_json(submission_dir, f)
    assert out["total"] == 0 and out["malformed"] == 0
    assert out["first_timestamp"] is None and out["latency_ms"] is None


@pytest.mark.edge
def test_top_zero_and_top_large(submission_dir):
    assert run_json(submission_dir, FIXTURES / "mixed.log", "--top", 0)["top_messages"] == []
    out = run_json(submission_dir, FIXTURES / "mixed.log", "--top", 1000)
    assert [m["message"] for m in out["top_messages"]] == [
        "GET /home", "Login ok", "Login failed", "Query failed", "Slow query"]
    assert [m["count"] for m in out["top_messages"]] == [3, 2, 1, 1, 1]


@pytest.mark.edge
def test_empty_template_included(submission_dir, tmp_path):
    lines = [
        "2024-01-01T00:00:00Z INFO svc user=1 latency_ms=3",
        "2024-01-01T00:00:00Z INFO svc user=2",
        "2024-01-01T00:00:00Z INFO svc hello",
    ]
    f = write_log(tmp_path, "et.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["top_messages"] == [{"message": "", "count": 2}, {"message": "hello", "count": 1}]


@pytest.mark.edge
def test_invalid_latency_value_ignored_line_still_valid(submission_dir, tmp_path):
    lines = [
        "2024-01-01T00:00:00Z INFO svc x latency_ms=abc",
        "2024-01-01T00:00:00Z INFO svc x latency_ms=",
        "2024-01-01T00:00:00Z INFO svc x latency_ms=1.5",
        "2024-01-01T00:00:00Z INFO svc x latency_ms=42",
    ]
    f = write_log(tmp_path, "il.log", "\n".join(lines) + "\n")
    out = run_json(submission_dir, f)
    assert out["total"] == 4 and out["malformed"] == 0
    assert out["latency_ms"] == {"count": 1, "min": 42, "max": 42, "avg": 42.0, "p95": 42}


@pytest.mark.edge
def test_exit_2_missing_file_no_stdout(submission_dir, tmp_path):
    p = run_cli(submission_dir, tmp_path / "does_not_exist.log")
    assert p.returncode == 2
    assert p.stdout.strip() == ""
    assert p.stderr.strip() != ""


@pytest.mark.edge
@pytest.mark.parametrize("args", [
    ("--top", "-1"),
    ("--top", "abc"),
    ("--level", "FOO"),
    ("--level", "info"),
    ("--since", "yesterday"),
    ("--until", "2024-01-01"),
])
def test_exit_1_invalid_args_no_stdout(submission_dir, args):
    p = run_cli(submission_dir, FIXTURES / "example.log", *args)
    assert p.returncode == 1, f"args={args} exit={p.returncode}"
    assert p.stdout.strip() == ""


@pytest.mark.edge
def test_unicode_message_and_service(submission_dir, tmp_path):
    f = write_log(tmp_path, "u.log", "2024-01-01T00:00:00Z INFO città Ciao è ünïcode user=1\n")
    out = run_json(submission_dir, f)
    assert out["by_service"] == {"città": {"count": 1, "errors": 0}}
    assert out["top_messages"] == [{"message": "Ciao è ünïcode", "count": 1}]


# ----------------------------------------------------------------- perf


@pytest.mark.perf
def test_perf_200k_lines(submission_dir, tmp_path):
    rnd = random.Random(1)
    levels = ["DEBUG", "INFO", "WARN", "ERROR"]
    services = [f"svc{i}" for i in range(20)]
    with open(tmp_path / "big.log", "w", encoding="utf-8") as fh:
        for i in range(200_000):
            ts = f"2024-01-{1 + (i % 28):02d}T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z"
            fh.write(f"{ts} {rnd.choice(levels)} {rnd.choice(services)} "
                     f"request /path{i % 500} user={i} latency_ms={rnd.randint(1, 1000)}\n")
    t0 = time.perf_counter()
    out = run_json(submission_dir, tmp_path / "big.log", "--top", 5, timeout=60)
    elapsed = time.perf_counter() - t0
    assert out["total"] == 200_000
    assert out["latency_ms"]["count"] == 200_000
    assert len(out["top_messages"]) == 5
    assert elapsed < 20, f"troppo lento: {elapsed:.1f}s"
