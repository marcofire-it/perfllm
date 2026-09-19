import unittest

from minilang import run, ParseError, MiniRuntimeError


class TestBasics(unittest.TestCase):
    def test_arithmetic_and_truncation(self):
        out = run("print(-7 / 2, -7 % 2, 7 / -2, 7 % -2);")
        self.assertEqual(out, "-3 -1 -3 1\n")

    def test_big_int_multiplication(self):
        out = run("print(123456789012345678901234567890 * 2);")
        self.assertEqual(out.strip(), str(123456789012345678901234567890 * 2))

    def test_string_concat_and_str(self):
        out = run('print(str(12) + "!", type(nil));')
        self.assertEqual(out, "12! nil\n")

    def test_list_shared_reference(self):
        out = run("""
        let a = [1, 2];
        let b = a;
        push(b, 3);
        print(a);
        """)
        self.assertEqual(out, "[1, 2, 3]\n")

    def test_list_literal_representation_nested(self):
        out = run('print([1, "a", [true, nil]]);')
        self.assertEqual(out, '[1, "a", [true, nil]]\n')

    def test_equality_structural_and_types(self):
        out = run('print(1 == "1", nil == nil, [1,[2,3]] == [1,[2,3]]);')
        self.assertEqual(out, "false true true\n")

    def test_short_circuit_and_or(self):
        out = run("print(false and (1/0 == 0));")
        self.assertEqual(out, "false\n")
        out = run("print(true or (1/0 == 0));")
        self.assertEqual(out, "true\n")

    def test_indexing_negative_and_string(self):
        out = run('print("abc"[1], "abc"[-1]);')
        self.assertEqual(out, "b c\n")

    def test_closures_capture_by_reference(self):
        out = run("""
        fn make_counter() {
          let n = 0;
          fn inc() { n = n + 1; return n; }
          return inc;
        }
        let c = make_counter();
        c(); c();
        print("count:", c());
        """)
        self.assertEqual(out, "count: 3\n")

    def test_recursion_depth_200(self):
        out = run(
            "fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); }"
            "print(count(200));"
        )
        self.assertEqual(out, "200\n")

    def test_scoping_shadowing(self):
        out = run("""
        let x = 1;
        { let x = 2; print(x); }
        print(x);
        """)
        self.assertEqual(out, "2\n1\n")

    def test_no_return_gives_nil(self):
        out = run("fn f() {} print(f());")
        self.assertEqual(out, "nil\n")

    def test_range_and_len(self):
        out = run("print(range(5), len(range(5)), range(-3));")
        self.assertEqual(out, "[0, 1, 2, 3, 4] 5 []\n")

    def test_int_conversion(self):
        out = run('print(int("42"), int("-7"), int(9));')
        self.assertEqual(out, "42 -7 9\n")


class TestParseErrors(unittest.TestCase):
    def test_missing_semicolon(self):
        with self.assertRaises(ParseError) as ctx:
            run("let x = 1\n")
        self.assertEqual(ctx.exception.line, 2)

    def test_break_outside_loop(self):
        with self.assertRaises(ParseError):
            run("break;")

    def test_continue_outside_loop(self):
        with self.assertRaises(ParseError):
            run("continue;")

    def test_return_outside_function(self):
        with self.assertRaises(ParseError):
            run("return 1;")

    def test_let_without_initializer(self):
        with self.assertRaises(ParseError):
            run("let x;")

    def test_unterminated_string(self):
        with self.assertRaises(ParseError):
            run('let s = "abc;')

    def test_invalid_char(self):
        with self.assertRaises(ParseError):
            run("let x = 1 @ 2;")

    def test_break_inside_function_inside_while_is_parse_error(self):
        # break dentro una funzione annidata non e' considerato dentro un
        # while dal punto di vista lessicale/di chiamata: deve fallire.
        with self.assertRaises(ParseError):
            run("""
            while (true) {
              fn f() { break; }
            }
            """)


class TestRuntimeErrors(unittest.TestCase):
    def test_type_mismatch_arithmetic(self):
        with self.assertRaises(MiniRuntimeError):
            run('print(1 + "a");')

    def test_condition_must_be_bool(self):
        with self.assertRaises(MiniRuntimeError):
            run("if (1) { print(1); }")

    def test_division_by_zero(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(1 / 0);")

    def test_modulo_by_zero(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(1 % 0);")

    def test_undeclared_variable_read(self):
        with self.assertRaises(MiniRuntimeError):
            run("print(x);")

    def test_undeclared_variable_assign(self):
        with self.assertRaises(MiniRuntimeError):
            run("x = 1;")

    def test_redeclare_same_scope(self):
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; let x = 2;")

    def test_index_out_of_range(self):
        with self.assertRaises(MiniRuntimeError):
            run("let xs = [1,2]; print(xs[5]);")

    def test_wrong_arity(self):
        with self.assertRaises(MiniRuntimeError):
            run("fn f(a, b) { return a + b; } f(1);")

    def test_call_non_function(self):
        with self.assertRaises(MiniRuntimeError):
            run("let x = 1; x();")

    def test_pop_empty_list(self):
        with self.assertRaises(MiniRuntimeError):
            run("let xs = []; pop(xs);")

    def test_output_recovered_on_error(self):
        try:
            run('print("before"); print(1 + "a");')
            self.fail("expected error")
        except MiniRuntimeError as e:
            self.assertEqual(e.output, "before\n")

    def test_error_line_inside_function_not_call_site(self):
        try:
            run("""
            fn boom() {
              return 1 / 0;
            }
            boom();
            """)
            self.fail("expected error")
        except MiniRuntimeError as e:
            self.assertEqual(e.line, 3)


if __name__ == "__main__":
    unittest.main()
