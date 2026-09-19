"""Test nascosti per il Task 03 (minilang).

Eseguire con: PERFLLM_SUBMISSION_DIR=<dir> python -m pytest evaluation/03-minilang -q
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import load_module_from

HERE = Path(__file__).parent
PROGRAMS = sorted((HERE / "programs").glob("*.ml"))


@pytest.fixture(scope="session")
def ml(submission_dir):
    return load_module_from(submission_dir, "minilang.py")


def _run_in_thread(fn, timeout):
    """Esegue fn in un thread daemon; fallisce il test se non termina entro timeout."""
    import threading

    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        pytest.fail(f"run() non ha terminato entro {timeout}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------


@pytest.mark.core
def test_api_surface(ml):
    assert callable(ml.run)
    assert issubclass(ml.ParseError, ml.MiniLangError)
    assert issubclass(ml.MiniRuntimeError, ml.MiniLangError)
    assert issubclass(ml.MiniLangError, Exception)


@pytest.mark.core
def test_import_has_no_side_effects(submission_dir):
    r = subprocess.run(
        [sys.executable, "-c", "import minilang; print('IMPORT_OK')"],
        cwd=submission_dir, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "IMPORT_OK"


@pytest.mark.core
def test_empty_program(ml):
    assert ml.run("") == ""
    assert ml.run("// solo un commento\n") == ""


# ----------------------------------------------------------------------------
# Programmi completi (output esatto)
# ----------------------------------------------------------------------------


@pytest.mark.core
@pytest.mark.parametrize("prog", PROGRAMS, ids=[p.stem for p in PROGRAMS])
def test_program(ml, prog):
    expected = prog.with_suffix(".expected").read_text(encoding="utf-8")
    source = prog.read_text(encoding="utf-8")
    assert _run_in_thread(lambda: ml.run(source), 60) == expected


# ----------------------------------------------------------------------------
# Errori di parsing (tipo + riga)
# ----------------------------------------------------------------------------


def _expect_parse_error(ml, src, line):
    with pytest.raises(ml.ParseError) as ei:
        ml.run(src)
    err = ei.value
    assert isinstance(err, ml.MiniLangError)
    assert err.line == line, f"line attesa {line}, trovata {err.line}: {err}"
    return err


PARSE_CASES = [
    ("missing_semicolon", 'let a = 1;\nlet x = 1 let y = 2;\n', 2),
    ("unterminated_string", 'let a = 1;\nlet s = "abc;\nprint(s);\n', 2),
    ("invalid_char", 'let a = 1;\nlet b = 2;\nlet c = a @ b;\n', 3),
    ("unbalanced_parens", 'print(1);\nprint((1 + 2);\n', 2),
    ("unbalanced_brackets", 'let xs = [1, 2;\n', 1),
    ("missing_brace_at_eof", 'if (true) { print(1);', 1),
    ("break_outside_loop", 'print(1);\nbreak;\n', 2),
    ("continue_outside_loop", 'fn f() {\n  continue;\n}\n', 2),
    ("return_top_level", 'let x = 1;\nreturn x;\n', 2),
    ("return_in_block_top_level", 'while (true) {\n  return 1;\n}\n', 2),
    ("let_without_initializer", 'let a = 1;\nlet x;\n', 2),
    ("if_without_parens", 'if true { print(1); }\n', 1),
    ("if_without_braces", 'if (true) print(1);\n', 1),
    ("assignment_to_literal", '1 = 2;\n', 1),
]


@pytest.mark.edge
@pytest.mark.parametrize("src,line", [(s, l) for _, s, l in PARSE_CASES],
                         ids=[c[0] for c in PARSE_CASES])
def test_parse_errors(ml, src, line):
    _expect_parse_error(ml, src, line)


@pytest.mark.edge
def test_parse_error_has_empty_output(ml):
    err = _expect_parse_error(ml, 'print(1);\nlet x = ;\n', 2)
    assert err.output == ""


# ----------------------------------------------------------------------------
# Errori runtime (tipo + riga)
# ----------------------------------------------------------------------------


def _expect_runtime_error(ml, src, line):
    with pytest.raises(ml.MiniRuntimeError) as ei:
        ml.run(src)
    err = ei.value
    assert isinstance(err, ml.MiniLangError)
    assert err.line == line, f"line attesa {line}, trovata {err.line}: {err}"
    return err


RUNTIME_CASES = [
    ("undefined_variable", 'let a = 1;\nlet b = 2;\nprint(a + c);\n', 3),
    ("assign_undeclared", 'let a = 1;\nb = 2;\n', 2),
    ("redeclare_same_scope", 'let a = 1;\nlet a = 2;\n', 2),
    ("redeclare_in_function", 'fn f() {\n  let x = 1;\n  let x = 2;\n}\nf();\n', 3),
    ("int_plus_string", 'let x = 1 + "a";\n', 1),
    ("string_minus", 'let x = "a" - "b";\n', 1),
    ("bool_plus", 'let x = true + true;\n', 1),
    ("if_non_bool", 'print(0);\nif (1) { print(1); }\n', 2),
    ("while_non_bool", 'while ("x") { break; }\n', 1),
    ("not_int", 'let x = not 5;\n', 1),
    ("neg_string", 'let x = -"a";\n', 1),
    ("compare_mixed", 'let x = "a" < 1;\n', 1),
    ("compare_lists", 'let x = [1] < [2];\n', 1),
    ("and_non_bool", 'let x = 1 and true;\n', 1),
    ("or_rhs_non_bool", 'let x = false or 1;\n', 1),
    ("division_by_zero", 'let a = 0;\nprint(10 / a);\n', 2),
    ("modulo_by_zero", 'print(10 % 0);\n', 1),
    ("index_out_of_range", 'let xs = [1, 2];\nprint(xs[2]);\n', 2),
    ("negative_index_out_of_range", 'let xs = [1, 2];\nprint(xs[-3]);\n', 2),
    ("string_index_out_of_range", 'print("ab"[5]);\n', 1),
    ("index_on_int", 'let n = 5;\nprint(n[0]);\n', 2),
    ("index_with_string", 'let xs = [1];\nprint(xs["0"]);\n', 2),
    ("index_assign_on_string", 'let s = "abc";\ns[0] = "z";\n', 2),
    ("call_non_function", 'let n = 5;\nn();\n', 2),
    ("call_nil", 'let f = nil;\nf(1);\n', 2),
    ("arity_too_few", 'fn add(a, b) { return a + b; }\nadd(1);\n', 2),
    ("arity_too_many", 'fn one(a) { return a; }\none(1, 2);\n', 2),
    ("builtin_arity", 'len();\n', 1),
    ("pop_empty", 'let xs = [];\npop(xs);\n', 2),
    ("push_non_list", 'push("s", 1);\n', 1),
    ("len_int", 'len(5);\n', 1),
    ("int_invalid_string", 'let n = int("abc");\n', 1),
    ("int_of_bool", 'let n = int(true);\n', 1),
    ("range_non_int", 'range("3");\n', 1),
    ("list_plus_int", 'let x = [1] + 1;\n', 1),
]


@pytest.mark.edge
@pytest.mark.parametrize("src,line", [(s, l) for _, s, l in RUNTIME_CASES],
                         ids=[c[0] for c in RUNTIME_CASES])
def test_runtime_errors(ml, src, line):
    _expect_runtime_error(ml, src, line)


@pytest.mark.edge
def test_redeclare_in_inner_scope_is_ok(ml):
    assert ml.run('let a = 1;\n{ let a = 2; print(a); }\nprint(a);\n') == "2\n1\n"
    assert ml.run('fn f(a) { return a; }\nlet a = 9;\nprint(f(1), a);\n') == "1 9\n"


@pytest.mark.edge
def test_runtime_error_line_inside_function(ml):
    src = (
        'fn boom(x) {\n'
        '  let y = x * 2;\n'
        '  return y + "s";\n'
        '}\n'
        'print("before");\n'
        'boom(1);\n'
        'print("after");\n'
    )
    err = _expect_runtime_error(ml, src, 3)
    assert err.output == "before\n"


@pytest.mark.edge
def test_runtime_error_preserves_output(ml):
    src = 'print(1);\nprint("two", [3]);\nlet z = 1 / 0;\nprint("never");\n'
    err = _expect_runtime_error(ml, src, 3)
    assert err.output == '1\ntwo [3]\n'


@pytest.mark.edge
def test_runtime_error_line_in_nested_call_chain(ml):
    src = (
        'fn inner() {\n'
        '  return undefined_name;\n'
        '}\n'
        'fn outer() {\n'
        '  return inner();\n'
        '}\n'
        'outer();\n'
    )
    _expect_runtime_error(ml, src, 2)


@pytest.mark.edge
def test_short_circuit_avoids_error(ml):
    assert ml.run('print(false and (1 / 0 == 0), true or (1 / 0 == 0));\n') == "false true\n"


@pytest.mark.edge
def test_list_shared_by_reference_across_function(ml):
    src = 'fn add(xs) { push(xs, 1); }\nlet a = [];\nadd(a); add(a);\nprint(a);\n'
    assert ml.run(src) == "[1, 1]\n"


@pytest.mark.edge
def test_string_comparison_codepoint(ml):
    assert ml.run('print("Z" < "a", "abc" < "abcd", "" < "a");\n') == "true true true\n"


@pytest.mark.edge
def test_deep_recursion_200(ml):
    src = 'fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); }\nprint(count(200));\n'
    assert _run_in_thread(lambda: ml.run(src), 60) == "200\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _cli(submission_dir, *args):
    return subprocess.run(
        [sys.executable, str(submission_dir / "minilang.py"), *args],
        capture_output=True, text=True, timeout=60, cwd=submission_dir,
    )


@pytest.mark.edge
def test_cli_ok(submission_dir, tmp_path):
    f = tmp_path / "ok.ml"
    f.write_text('let x = [1, "a"];\nprint("hi", x, 2 * 21);\n', encoding="utf-8")
    r = _cli(submission_dir, str(f))
    assert r.returncode == 0, r.stderr
    assert r.stdout.replace("\r\n", "\n") == 'hi [1, "a"] 42\n'


@pytest.mark.edge
def test_cli_runtime_error(submission_dir, tmp_path):
    f = tmp_path / "rt.ml"
    f.write_text('print("partial");\nlet x = 1;\nprint(x / 0);\n', encoding="utf-8")
    r = _cli(submission_dir, str(f))
    assert r.returncode == 1
    assert r.stdout.replace("\r\n", "\n") == "partial\n"
    assert r.stderr.strip().startswith("RuntimeError: line 3:"), r.stderr


@pytest.mark.edge
def test_cli_parse_error(submission_dir, tmp_path):
    f = tmp_path / "pe.ml"
    f.write_text('print(1);\nlet = 5;\n', encoding="utf-8")
    r = _cli(submission_dir, str(f))
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip().startswith("ParseError: line 2:"), r.stderr


@pytest.mark.edge
def test_cli_missing_file(submission_dir, tmp_path):
    r = _cli(submission_dir, str(tmp_path / "does_not_exist.ml"))
    assert r.returncode == 2
    assert r.stdout == ""


# ----------------------------------------------------------------------------
# Prestazioni
# ----------------------------------------------------------------------------


@pytest.mark.perf
def test_perf_loop_300k(ml):
    src = 'let i = 0;\nlet s = 0;\nwhile (i < 300000) { s = s + i * 2; i = i + 1; }\nprint(s);\n'
    t0 = time.perf_counter()
    out = _run_in_thread(lambda: ml.run(src), 30)
    elapsed = time.perf_counter() - t0
    assert out == f"{sum(i * 2 for i in range(300000))}\n"
    assert elapsed < 10, f"loop di 300k iterazioni in {elapsed:.1f}s (limite 10s)"


@pytest.mark.perf
def test_perf_fib_25(ml):
    src = 'fn fib(n) { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); }\nprint(fib(25));\n'
    t0 = time.perf_counter()
    out = _run_in_thread(lambda: ml.run(src), 60)
    elapsed = time.perf_counter() - t0
    assert out == "75025\n"
    assert elapsed < 20, f"fib(25) in {elapsed:.1f}s (limite 20s)"
