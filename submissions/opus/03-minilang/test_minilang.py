#!/usr/bin/env python3
"""Tests for minilang.py"""

import unittest
import time
from minilang import run, ParseError, MiniRuntimeError


class TestLexerBasic(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(run(""), "")

    def test_comment_only(self):
        self.assertEqual(run("// nothing here\n"), "")

    def test_unterminated_string(self):
        with self.assertRaises(ParseError):
            run('let x = "hello;')

    def test_invalid_escape(self):
        with self.assertRaises(ParseError):
            run(r'let x = "\q";')

    def test_unexpected_char(self):
        with self.assertRaises(ParseError):
            run("let x = @;")


class TestPrint(unittest.TestCase):
    def test_print_no_args(self):
        self.assertEqual(run("print();"), "\n")

    def test_print_int(self):
        self.assertEqual(run("print(42);"), "42\n")

    def test_print_string(self):
        self.assertEqual(run('print("hello");'), "hello\n")

    def test_print_bool(self):
        self.assertEqual(run("print(true, false);"), "true false\n")

    def test_print_nil(self):
        self.assertEqual(run("print(nil);"), "nil\n")

    def test_print_list(self):
        self.assertEqual(run('print([1, "a", [true, nil]]);'),
                         '[1, "a", [true, nil]]\n')

    def test_print_function(self):
        self.assertEqual(run("print(print);"), "<function>\n")

    def test_print_multiple(self):
        self.assertEqual(run("print(1, 2, 3);"), "1 2 3\n")


class TestArithmetic(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(run("print(1 + 2 * 3);"), "7\n")

    def test_parens(self):
        self.assertEqual(run("print((1 + 2) * 3);"), "9\n")

    def test_unary_minus(self):
        self.assertEqual(run("print(-5);"), "-5\n")

    def test_div_trunc_toward_zero(self):
        self.assertEqual(run("print(-7 / 2);"), "-3\n")
        self.assertEqual(run("print(7 / -2);"), "-3\n")
        self.assertEqual(run("print(-7 / -2);"), "3\n")
        self.assertEqual(run("print(7 / 2);"), "3\n")

    def test_mod_sign_of_dividend(self):
        self.assertEqual(run("print(-7 % 2);"), "-1\n")
        self.assertEqual(run("print(7 % -2);"), "1\n")
        self.assertEqual(run("print(-7 % -2);"), "-1\n")
        self.assertEqual(run("print(7 % 2);"), "1\n")

    def test_div_by_zero(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(1 / 0);")

    def test_mod_by_zero(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(1 % 0);")

    def test_large_int(self):
        out = run("print(99999999999999999999 * 99999999999999999999);")
        self.assertEqual(out, "9999999999999999999800000000000000000001\n")

    def test_type_error_add(self):
        with self.assertRaises(MiniRuntimeError):
            run('print(1 + "a");')


class TestComparison(unittest.TestCase):
    def test_int_lt(self):
        self.assertEqual(run("print(1 < 2);"), "true\n")

    def test_int_ge(self):
        self.assertEqual(run("print(2 >= 2);"), "true\n")

    def test_string_cmp(self):
        self.assertEqual(run('print("abc" < "abd");'), "true\n")

    def test_eq_diff_types(self):
        self.assertEqual(run('print(1 == "1");'), "false\n")

    def test_eq_nil(self):
        self.assertEqual(run("print(nil == nil);"), "true\n")

    def test_eq_bool(self):
        self.assertEqual(run("print(true == true);"), "true\n")
        self.assertEqual(run("print(true == false);"), "false\n")

    def test_eq_list_structural(self):
        self.assertEqual(run("print([1, 2] == [1, 2]);"), "true\n")
        self.assertEqual(run("print([1, 2] == [1, 3]);"), "false\n")

    def test_eq_fn_identity(self):
        self.assertEqual(run("""
let f = fn(x) { return x; };
let g = f;
print(f == g);
print(f == fn(x) { return x; });
"""), "true\nfalse\n")

    def test_cmp_type_error(self):
        with self.assertRaises(MiniRuntimeError):
            run('print(1 < "a");')


class TestBoolOps(unittest.TestCase):
    def test_and_short_circuit(self):
        self.assertEqual(run("print(false and (1/0 == 0));"), "false\n")

    def test_or_short_circuit(self):
        self.assertEqual(run("print(true or (1/0 == 0));"), "true\n")

    def test_not(self):
        self.assertEqual(run("print(not true);"), "false\n")

    def test_not_type_error(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(not 1);")

    def test_and_type_error(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(1 and true);")

    def test_condition_must_be_bool(self):
        with self.assertRaises(MiniRuntimeError):
            run("if (1) { print(1); }")

    def test_while_condition_must_be_bool(self):
        with self.assertRaises(MiniRuntimeError):
            run("while (1) { print(1); }")


class TestVariables(unittest.TestCase):
    def test_let_and_use(self):
        self.assertEqual(run("let x = 42; print(x);"), "42\n")

    def test_assign(self):
        self.assertEqual(run("let x = 1; x = 2; print(x);"), "2\n")

    def test_undefined_read(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(x);")

    def test_undefined_assign(self):
        with self.assertRaises(MiniRuntimeError):
            run("x = 1;")

    def test_redeclare_same_scope(self):
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; let x = 2;")

    def test_shadow_in_block(self):
        self.assertEqual(run("""
let x = 1;
{
    let x = 2;
    print(x);
}
print(x);
"""), "2\n1\n")


class TestIfElse(unittest.TestCase):
    def test_if_true(self):
        self.assertEqual(run("if (true) { print(1); }"), "1\n")

    def test_if_false(self):
        self.assertEqual(run("if (false) { print(1); }"), "")

    def test_if_else(self):
        self.assertEqual(run("""
if (false) { print(1); } else { print(2); }
"""), "2\n")

    def test_else_if(self):
        self.assertEqual(run("""
let x = 3;
if (x == 1) { print("a"); }
else if (x == 2) { print("b"); }
else if (x == 3) { print("c"); }
else { print("d"); }
"""), "c\n")


class TestWhile(unittest.TestCase):
    def test_basic_loop(self):
        self.assertEqual(run("""
let i = 0;
while (i < 5) {
    print(i);
    i = i + 1;
}
"""), "0\n1\n2\n3\n4\n")

    def test_break(self):
        self.assertEqual(run("""
let i = 0;
while (true) {
    if (i == 3) { break; }
    print(i);
    i = i + 1;
}
"""), "0\n1\n2\n")

    def test_continue(self):
        self.assertEqual(run("""
let i = 0;
while (i < 5) {
    i = i + 1;
    if (i == 3) { continue; }
    print(i);
}
"""), "1\n2\n4\n5\n")

    def test_break_outside_loop(self):
        with self.assertRaises(ParseError):
            run("break;")

    def test_continue_outside_loop(self):
        with self.assertRaises(ParseError):
            run("continue;")


class TestFunctions(unittest.TestCase):
    def test_basic_fn(self):
        self.assertEqual(run("""
fn add(a, b) { return a + b; }
print(add(3, 4));
"""), "7\n")

    def test_no_return(self):
        self.assertEqual(run("""
fn noop() { let x = 1; }
print(noop());
"""), "nil\n")

    def test_return_nil(self):
        self.assertEqual(run("""
fn f() { return; }
print(f());
"""), "nil\n")

    def test_wrong_arity(self):
        with self.assertRaises(MiniRuntimeError):
            run("fn f(a) { return a; } f(1, 2);")

    def test_call_non_function(self):
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; x();")

    def test_return_outside_function(self):
        with self.assertRaises(ParseError):
            run("return 1;")

    def test_recursion_200(self):
        out = run("""
fn count(n) {
    if (n == 0) { return 0; }
    return 1 + count(n - 1);
}
print(count(200));
""")
        self.assertEqual(out, "200\n")

    def test_anonymous_fn(self):
        self.assertEqual(run("""
let add = fn(a, b) { return a + b; };
print(add(1, 2));
"""), "3\n")

    def test_first_class(self):
        self.assertEqual(run("""
fn apply(f, x) { return f(x); }
fn double(n) { return n * 2; }
print(apply(double, 5));
"""), "10\n")

    def test_iife(self):
        self.assertEqual(run("""
print(fn(x) { return x + 1; }(41));
"""), "42\n")

    def test_break_in_fn_in_loop(self):
        """break inside a function defined inside a while is a ParseError."""
        with self.assertRaises(ParseError):
            run("""
while (true) {
    fn f() { break; }
    f();
}
""")


class TestClosure(unittest.TestCase):
    def test_counter(self):
        self.assertEqual(run("""
fn make_counter() {
    let n = 0;
    fn inc() { n = n + 1; return n; }
    return inc;
}
let c = make_counter();
c(); c();
print(c());
"""), "3\n")

    def test_capture_by_reference(self):
        self.assertEqual(run("""
fn make() {
    let x = 10;
    let get = fn() { return x; };
    let set = fn(v) { x = v; };
    return [get, set];
}
let gs = make();
let getter = gs[0];
let setter = gs[1];
print(getter());
setter(42);
print(getter());
"""), "10\n42\n")


class TestLists(unittest.TestCase):
    def test_literal(self):
        self.assertEqual(run("print([1, 2, 3]);"), "[1, 2, 3]\n")

    def test_empty(self):
        self.assertEqual(run("print([]);"), "[]\n")

    def test_index(self):
        self.assertEqual(run("let xs = [10, 20, 30]; print(xs[1]);"), "20\n")

    def test_negative_index(self):
        self.assertEqual(run("let xs = [10, 20, 30]; print(xs[-1]);"), "30\n")

    def test_index_out_of_range(self):
        with self.assertRaises(MiniRuntimeError):
            run("let xs = [1]; print(xs[5]);")

    def test_index_assign(self):
        self.assertEqual(run("""
let xs = [1, 2, 3];
xs[1] = 99;
print(xs);
"""), "[1, 99, 3]\n")

    def test_shared_reference(self):
        self.assertEqual(run("""
let a = [1, 2];
let b = a;
push(b, 3);
print(a);
"""), "[1, 2, 3]\n")

    def test_concat(self):
        self.assertEqual(run("print([1, 2] + [3, 4]);"), "[1, 2, 3, 4]\n")

    def test_string_index(self):
        self.assertEqual(run('let s = "abc"; print(s[0], s[-1]);'), "a c\n")

    def test_push_pop(self):
        self.assertEqual(run("""
let xs = [];
push(xs, 10);
push(xs, 20);
print(pop(xs));
print(xs);
"""), "20\n[10]\n")

    def test_pop_empty(self):
        with self.assertRaises(MiniRuntimeError):
            run("pop([]);")

    def test_len(self):
        self.assertEqual(run('print(len([1,2,3]), len("abc"));'), "3 3\n")

    def test_nested_index_assign(self):
        self.assertEqual(run("""
let m = [[1, 2], [3, 4]];
m[0][1] = 99;
print(m);
"""), "[[1, 99], [3, 4]]\n")


class TestBuiltins(unittest.TestCase):
    def test_str_int(self):
        self.assertEqual(run('print(str(42) + "!");'), "42!\n")

    def test_int_str(self):
        self.assertEqual(run('print(int("123"));'), "123\n")

    def test_int_negative_str(self):
        self.assertEqual(run('print(int("-5"));'), "-5\n")

    def test_int_identity(self):
        self.assertEqual(run("print(int(7));"), "7\n")

    def test_int_bad_str(self):
        with self.assertRaises(MiniRuntimeError):
            run('int("abc");')

    def test_type(self):
        self.assertEqual(run("""
print(type(1), type(true), type("x"), type(nil), type([]), type(print));
"""), "int bool string nil list function\n")

    def test_range(self):
        self.assertEqual(run("print(range(5));"), "[0, 1, 2, 3, 4]\n")

    def test_range_negative(self):
        self.assertEqual(run("print(range(-1));"), "[]\n")

    def test_shadow_builtin(self):
        self.assertEqual(run("""
{
    let len = fn(x) { return 42; };
    print(len("hi"));
}
"""), "42\n")


class TestStringConcat(unittest.TestCase):
    def test_concat(self):
        self.assertEqual(run('print("a" + "b" + "c");'), "abc\n")


class TestComplexExample(unittest.TestCase):
    def test_spec_example(self):
        prog = r"""
// closure e liste
fn make_counter() {
  let n = 0;
  fn inc() { n = n + 1; return n; }
  return inc;
}
let c = make_counter();
c(); c();
print("count:", c());

let xs = [3, 1, 2];
fn sort(v) {
  let i = 0;
  while (i < len(v)) {
    let j = 0;
    while (j < len(v) - 1 - i) {
      if (v[j] > v[j + 1]) { let t = v[j]; v[j] = v[j + 1]; v[j + 1] = t; }
      j = j + 1;
    }
    i = i + 1;
  }
}
sort(xs);
print(xs, len(xs), xs[-1]);
print(-7 / 2, -7 % 2, 7 / -2);
print(str(12) + "!", type(nil));
"""
        expected = "count: 3\n[1, 2, 3] 3 3\n-3 -1 -3\n12! nil\n"
        self.assertEqual(run(prog), expected)


class TestErrorOutput(unittest.TestCase):
    def test_output_before_error(self):
        try:
            run("""
print("ok");
print(1 + "a");
""")
            self.fail("Expected MiniRuntimeError")
        except MiniRuntimeError as e:
            self.assertEqual(e.output, "ok\n")
            self.assertIsInstance(e.line, int)
            self.assertGreater(e.line, 0)

    def test_parse_error_line(self):
        try:
            run("let x = ;")
            self.fail("Expected ParseError")
        except ParseError as e:
            self.assertIsInstance(e.line, int)
            self.assertEqual(e.output, "")


class TestEdgeCases(unittest.TestCase):
    def test_nested_fn_calls(self):
        self.assertEqual(run("""
fn a(x) { return fn(y) { return x + y; }; }
print(a(10)(20));
"""), "30\n")

    def test_chained_index(self):
        self.assertEqual(run("""
let m = [[1, 2], [3, 4]];
print(m[1][0]);
"""), "3\n")

    def test_bool_not_int(self):
        """true and 1 are different types."""
        self.assertEqual(run("print(true == 1);"), "false\n")
        self.assertEqual(run("print(false == 0);"), "false\n")

    def test_nil_not_false(self):
        self.assertEqual(run("print(nil == false);"), "false\n")

    def test_string_escape(self):
        self.assertEqual(run(r'print("a\nb\tc\\d\"e");'),
                         'a\nb\tc\\d"e\n')

    def test_empty_list_equality(self):
        self.assertEqual(run("print([] == []);"), "true\n")

    def test_list_structural_deep(self):
        self.assertEqual(run("print([[1, [2]]] == [[1, [2]]]);"), "true\n")
        self.assertEqual(run("print([[1, [2]]] == [[1, [3]]]);"), "false\n")

    def test_string_index_negative(self):
        self.assertEqual(run('print("hello"[-1]);'), "o\n")

    def test_string_index_oor(self):
        with self.assertRaises(MiniRuntimeError):
            run('print("ab"[5]);')

    def test_index_assign_string_error(self):
        """Strings are immutable; index-assign should fail."""
        with self.assertRaises(MiniRuntimeError):
            run('let s = "abc"; s[0] = "x";')

    def test_nested_block_scope(self):
        self.assertEqual(run("""
let x = 1;
{
    let x = 2;
    {
        let x = 3;
        print(x);
    }
    print(x);
}
print(x);
"""), "3\n2\n1\n")


class TestPerformance(unittest.TestCase):
    def test_300k_loop(self):
        prog = """
let i = 0;
let s = 0;
while (i < 300000) {
    s = s + i;
    i = i + 1;
}
print(s);
"""
        start = time.time()
        out = run(prog)
        elapsed = time.time() - start
        self.assertEqual(out, str(300000 * 299999 // 2) + "\n")
        self.assertLess(elapsed, 10.0, f"Took {elapsed:.1f}s (limit 10s)")


if __name__ == "__main__":
    unittest.main()
