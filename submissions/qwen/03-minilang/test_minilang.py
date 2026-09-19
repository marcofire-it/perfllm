import sys
import time
import unittest

from minilang import run, ParseError, MiniRuntimeError, MiniLangError


class TestMiniLang(unittest.TestCase):
    def test_example(self):
        src = '''
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
'''
        self.assertEqual(
            run(src),
            "count: 3\n[1, 2, 3] 3 3\n-3 -1 -3\n12! nil\n",
        )

    def test_arithmetic(self):
        self.assertEqual(run("print(1 + 2 * 3);"), "7\n")
        self.assertEqual(run("print((1 + 2) * 3);"), "9\n")
        self.assertEqual(run("print(-7 / 2, -7 % 2, 7 / -2, 7 % -2);"), "-3 -1 -3 1\n")
        self.assertEqual(run("print(-10 / 3, 10 / -3, -10 % 3, 10 % -3);"), "-3 -3 -1 1\n")
        self.assertEqual(run("print(2 * 3 - 4 + 1);"), "3\n")
        # big ints (no overflow)
        big = "999999999999999999999999999999999999 * 2"
        self.assertEqual(run("print(%s);" % big), "1999999999999999999999999999999999998\n")

    def test_strings(self):
        self.assertEqual(run(r'print("a\tb\"c");'), 'a\tb"c\n')
        self.assertEqual(run('print("a" + "b", len("abc"));'), "ab 3\n")
        self.assertEqual(run('print("abc"[1], "abc"[-1], len("abc"[0]));'), "b c 1\n")
        self.assertEqual(run(r'print(str("x"));'), "x\n")

    def test_lists(self):
        self.assertEqual(run('print([1, "a", [true, nil]]);'), '[1, "a", [true, nil]]\n')
        self.assertEqual(run("print([]);"), "[]\n")
        self.assertEqual(run("let a = [1, 2]; let b = a; push(b, 3); print(a, b);"), "[1, 2, 3] [1, 2, 3]\n")
        self.assertEqual(run("let a = [1]; let b = a; a[0] = 9; print(b);"), "[9]\n")
        self.assertEqual(run("let a = [1, 2]; a[1] = 5; print(a, a[-2]);"), "[1, 5] 1\n")
        self.assertEqual(run("let a = [1, 2]; let b = a + [3]; push(a, 9); print(a, b);"), "[1, 2, 9] [1, 2, 3]\n")
        self.assertEqual(run("print(pop([1, 2, 3]), [1, 2, 3]);"), "3 [1, 2, 3]\n")
        self.assertEqual(run("print([1] == [1], [1] == [2], [1, [2]] == [1, [2]]);"), "true false true\n")

    def test_bool_logic(self):
        self.assertEqual(run("print(true and false, false and (1 == 1), true or false, false or true, not true);"),
                         "false false true true false\n")
        # short-circuit: right side not evaluated
        self.assertEqual(run("print(false and (1 / 0 == 0));"), "false\n")
        self.assertEqual(run("print(true or (1 / 0 == 0));"), "true\n")
        # non-bool operand is a runtime error
        with self.assertRaises(MiniRuntimeError):
            run("print(1 and true);")
        with self.assertRaises(MiniRuntimeError):
            run("print(not 1);")
        with self.assertRaises(MiniRuntimeError):
            run("if (1) { }")

    def test_equality(self):
        self.assertEqual(run('print(1 == "1", 1 == true, nil == nil, "a" == "a");'), "false false true true\n")
        self.assertEqual(run('print(1 != "1", nil != 0);'), "true true\n")

    def test_comparison(self):
        self.assertEqual(run('print(1 < 2, 2 <= 2, "a" < "b", "ab" < "abc");'), "true true true true\n")
        with self.assertRaises(MiniRuntimeError):
            run('print(1 < "a");')
        with self.assertRaises(MiniRuntimeError):
            run("print(true < false);")

    def test_type_errors(self):
        with self.assertRaises(MiniRuntimeError):
            run('print(1 + "a");')
        with self.assertRaises(MiniRuntimeError):
            run("print(1 / 0);")
        with self.assertRaises(MiniRuntimeError):
            run("print(1 % 0);")
        with self.assertRaises(MiniRuntimeError):
            run("print(1 - true);")
        with self.assertRaises(MiniRuntimeError):
            run("print(-true);")

    def test_scoping(self):
        # shadowing
        self.assertEqual(run("let x = 1; { let x = 2; print(x); } print(x);"), "2\n1\n")
        # redeclaration in same scope
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; let x = 2;")
        with self.assertRaises(MiniRuntimeError):
            run("fn f() { let x = 1; let x = 2; } f();")
        # assign to undeclared
        with self.assertRaises(MiniRuntimeError):
            run("y = 1;")
        # read undeclared
        with self.assertRaises(MiniRuntimeError):
            run("print(y);")
        # block scopes don't leak
        with self.assertRaises(MiniRuntimeError):
            run("{ let x = 1; } print(x);")

    def test_closures(self):
        self.assertEqual(
            run("""
let n = 10;
fn inc() { n = n + 1; return n; }
inc();
print(n, inc());
"""),
            "11 12\n",
        )
        # closures over loop variables (each iteration declares its own i)
        self.assertEqual(
            run("""
let fs = [];
let k = 0;
while (k < 3) {
  let i = k;
  let f = fn () { return i; };
  push(fs, f);
  k = k + 1;
}
print(fs[0](), fs[1](), fs[2]());
"""),
            "0 1 2\n",
        )

    def test_functions(self):
        self.assertEqual(run("fn f() { } print(f());"), "nil\n")
        self.assertEqual(run("print(fn (x) { return x; }(42));"), "42\n")
        self.assertEqual(run("let f = fn (x) { return x * 2; }; print(f(21));"), "42\n")
        self.assertEqual(
            run("let g = fn (x) { return fn (y) { return x + y; }; }; print(g(1)(2));"),
            "3\n",
        )
        self.assertEqual(run("let h = fn (x) { return x; }; let k = h; print(h == k, h == fn () { });"), "true false\n")
        with self.assertRaises(MiniRuntimeError):
            run("fn f(a) { } f(1, 2);")
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; x(2);")
        with self.assertRaises(MiniRuntimeError):
            run("fn f(a) { } f();")

    def test_recursion(self):
        self.assertEqual(
            run("fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); } print(count(200));"),
            "200\n",
        )
        self.assertEqual(
            run("fn fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); } print(fact(20));"),
            "2432902008176640000\n",
        )

    def test_control_flow(self):
        self.assertEqual(
            run("""
let i = 0;
let s = "";
while (i < 10) {
  if (i == 3) { i = i + 1; continue; }
  if (i == 7) { break; }
  s = s + str(i);
  i = i + 1;
}
print(s);
"""),
            "012456\n",
        )
        self.assertEqual(run("if (true) { print(1); } else { print(2); }"), "1\n")
        self.assertEqual(
            run("if (1 < 2) { print(1); } else if (2 < 3) { print(2); } else { print(3); }"),
            "1\n",
        )
        self.assertEqual(
            run("if (1 > 2) { print(1); } else if (2 < 3) { print(2); } else { print(3); }"),
            "2\n",
        )
        self.assertEqual(
            run("if (1 > 2) { print(1); } else if (3 < 2) { print(2); } else { print(3); }"),
            "3\n",
        )

    def test_builtins(self):
        self.assertEqual(run("print();"), "\n")
        self.assertEqual(run('print(type(1), type(true), type("s"), type([]), type(print), type(nil));'),
                         "int bool string list function nil\n")
        self.assertEqual(run('print(int("123"), int("-45"), int(7));'), "123 -45 7\n")
        with self.assertRaises(MiniRuntimeError):
            run('print(int("12a"));')
        with self.assertRaises(MiniRuntimeError):
            run('print(int(""));')
        with self.assertRaises(MiniRuntimeError):
            run('print(int("-"));')
        self.assertEqual(run("print(range(5), range(0), range(-3));"), "[0, 1, 2, 3, 4] [] []\n")
        with self.assertRaises(MiniRuntimeError):
            run("print(range(\"5\"));")
        with self.assertRaises(MiniRuntimeError):
            run("print(len(1));")
        with self.assertRaises(MiniRuntimeError):
            run("print(pop([]));")
        with self.assertRaises(MiniRuntimeError):
            run("print(push(1, 2));")
        # builtins can be shadowed in an inner scope (top-level `let len`
        # would be a same-scope redeclaration and is a runtime error)
        self.assertEqual(run("{ let len = 5; print(len); } print(len(\"ab\"));"), "5\n2\n")

    def test_index_errors(self):
        with self.assertRaises(MiniRuntimeError):
            run("print([1][5]);")
        with self.assertRaises(MiniRuntimeError):
            run("print([1][-2]);")
        with self.assertRaises(MiniRuntimeError):
            run('print("ab"[2]);')
        with self.assertRaises(MiniRuntimeError):
            run('print("ab"[-3]);')
        with self.assertRaises(MiniRuntimeError):
            run("let a = [1]; a[5] = 2;")
        with self.assertRaises(MiniRuntimeError):
            run('let s = "ab"; s[0] = "c";')
        with self.assertRaises(MiniRuntimeError):
            run("print([1][true]);")

    def test_parse_errors(self):
        parse_cases = [
            "let x;",                  # let without initializer
            "let = 1;",                # missing name
            "x 1",                     # missing ';'
            "(1 + 2",                  # unbalanced parens
            "let x = (1; print(x);",   # unbalanced parens
            '{ let x = 1;',            # unterminated block
            'break;',                  # break outside while
            'continue;',               # continue outside while
            'return 1;',               # return outside function
            "let x = 1 2;",            # missing ';'
            "print(@)",                # invalid char
            'print("abc)',             # unterminated string
        ]
        for src in parse_cases:
            with self.assertRaises(ParseError, msg=src):
                run(src)
        runtime_cases = [
            'while (1) { break; }',    # non-bool while condition
            "let x = 1; let x = 2;",   # same-scope redeclaration
        ]
        for src in runtime_cases:
            with self.assertRaises(MiniRuntimeError, msg=src):
                run(src)

    def test_error_output_and_line(self):
        try:
            run('print("before");\nlet x = 1;\nprint(x / 0);')
            self.fail("expected MiniRuntimeError")
        except MiniRuntimeError as e:
            self.assertEqual(e.output, "before\n")
            self.assertEqual(e.line, 3)
        try:
            run('print("ok");\nlet y = ;')
            self.fail("expected ParseError")
        except ParseError as e:
            self.assertEqual(e.output, "")
            self.assertEqual(e.line, 2)
        # runtime error inside a function: line of the failing expression
        try:
            run('fn f() { print(1 / 0); }\nprint("x");\nf();')
            self.fail("expected MiniRuntimeError")
        except MiniRuntimeError as e:
            self.assertEqual(e.line, 1)
            self.assertEqual(e.output, "x\n")
        self.assertIsInstance(ParseError(1, "x"), MiniLangError)
        self.assertIsInstance(MiniRuntimeError(1, "x"), MiniLangError)

    def test_index_assign_and_string_index(self):
        self.assertEqual(run('let s = "hello"; print(s[0], s[4]);'), "h o\n")
        self.assertEqual(run("let a = [[1, 2], [3, 4]]; print(a[1][0], a[0][1]);"), "3 2\n")
        self.assertEqual(run("let a = [[1, 2]]; a[0][1] = 9; print(a);"), "[[1, 9]]\n")

    def test_comments_and_whitespace(self):
        self.assertEqual(run("// comment\nlet x = 1; // trailing\nprint(x); // end"), "1\n")
        self.assertEqual(run("let\tx=1;\nprint(x);"), "1\n")

    def test_empty_program(self):
        self.assertEqual(run(""), "")
        self.assertEqual(run("// only a comment\n"), "")

    def test_precedence(self):
        self.assertEqual(run("print(not true == false);"), "true\n")  # not binds tighter than ==
        self.assertEqual(run("print(-2 * 3);"), "-6\n")
        self.assertEqual(run("print(10 - 2 - 3);"), "5\n")  # left assoc
        self.assertEqual(run("print(20 / 2 / 5);"), "2\n")
        self.assertEqual(run("print(1 < 2 and 2 < 3 or 5 < 4);"), "true\n")
        self.assertEqual(run("print(2 + 3 * 4 == 14);"), "true\n")

    def test_while_performance(self):
        src = "let i = 0; let s = 0; while (i < 300000) { s = s + i; i = i + 1; } print(s);"
        t0 = time.time()
        out = run(src)
        dt = time.time() - t0
        self.assertEqual(out, str(300000 * 299999 // 2) + "\n")
        self.assertLess(dt, 10.0, "300k-iteration loop took %.1fs" % dt)


if __name__ == "__main__":
    unittest.main()
