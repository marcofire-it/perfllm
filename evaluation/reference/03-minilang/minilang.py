"""MiniLang — implementazione di riferimento (lexer + parser + compilatore a closure).

Uso come libreria:  from minilang import run, ParseError, MiniRuntimeError
Uso da CLI:         python minilang.py programma.ml
"""
from __future__ import annotations

import re
import sys

# ----------------------------------------------------------------------------
# Errori
# ----------------------------------------------------------------------------


class MiniLangError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(message)
        self.message = message
        self.line = line
        self.output = ""

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


class ParseError(MiniLangError):
    pass


class MiniRuntimeError(MiniLangError):
    pass


# ----------------------------------------------------------------------------
# Lexer
# ----------------------------------------------------------------------------

KEYWORDS = {
    "let", "fn", "return", "if", "else", "while", "break", "continue",
    "and", "or", "not", "true", "false", "nil",
}
TWO_CHAR_OPS = {"==", "!=", "<=", ">="}
ONE_CHAR_OPS = set("+-*/%()[]{},;=<>")
ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


class Token:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind: str, value, line: int):
        self.kind = kind      # "INT" | "STR" | "ID" | "EOF" | keyword | operator
        self.value = value
        self.line = line

    def __repr__(self) -> str:  # pragma: no cover
        return f"Token({self.kind!r}, {self.value!r}, {self.line})"


def tokenize(src: str) -> list[Token]:
    toks: list[Token] = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "/" and src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif c.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            toks.append(Token("INT", int(src[i:j]), line))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            toks.append(Token(word if word in KEYWORDS else "ID", word, line))
            i = j
        elif c == '"':
            start_line = line
            j = i + 1
            buf: list[str] = []
            while True:
                if j >= n or src[j] == "\n":
                    raise ParseError("unterminated string", start_line)
                ch = src[j]
                if ch == '"':
                    break
                if ch == "\\":
                    j += 1
                    if j >= n or src[j] not in ESCAPES:
                        raise ParseError("invalid escape sequence", start_line)
                    buf.append(ESCAPES[src[j]])
                else:
                    buf.append(ch)
                j += 1
            toks.append(Token("STR", "".join(buf), start_line))
            i = j + 1
        elif src[i:i + 2] in TWO_CHAR_OPS:
            toks.append(Token(src[i:i + 2], src[i:i + 2], line))
            i += 2
        elif c in ONE_CHAR_OPS:
            toks.append(Token(c, c, line))
            i += 1
        else:
            raise ParseError(f"unexpected character {c!r}", line)
    toks.append(Token("EOF", None, line))
    return toks


# ----------------------------------------------------------------------------
# AST (tuple: (kind, line, ...))
# ----------------------------------------------------------------------------


class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0
        self.loop_depth = 0
        self.fn_depth = 0

    # -- helpers ------------------------------------------------------------
    def peek(self, k: int = 0) -> Token:
        return self.toks[self.i + k]

    def advance(self) -> Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def check(self, kind: str) -> bool:
        return self.toks[self.i].kind == kind

    def expect(self, kind: str) -> Token:
        t = self.toks[self.i]
        if t.kind != kind:
            found = "end of input" if t.kind == "EOF" else repr(t.value)
            raise ParseError(f"expected '{kind}' but found {found}", t.line)
        self.i += 1
        return t

    # -- program / statements ------------------------------------------------
    def parse_program(self) -> list:
        stmts = []
        while not self.check("EOF"):
            stmts.append(self.parse_statement())
        return stmts

    def parse_block(self) -> tuple:
        lbrace = self.expect("{")
        stmts = []
        while not self.check("}"):
            if self.check("EOF"):
                raise ParseError("expected '}' but found end of input", self.peek().line)
            stmts.append(self.parse_statement())
        self.expect("}")
        return ("block", lbrace.line, stmts)

    def parse_statement(self) -> tuple:
        t = self.peek()
        k = t.kind
        if k == "let":
            self.advance()
            name = self.expect("ID")
            if not self.check("="):
                raise ParseError("'let' requires an initializer", self.peek().line)
            self.advance()
            expr = self.parse_expression()
            self.expect(";")
            return ("let", t.line, name.value, expr)
        if k == "fn" and self.peek(1).kind == "ID":
            self.advance()
            name = self.advance()
            params, body = self.parse_fn_rest()
            return ("let", t.line, name.value, ("fn", t.line, params, body))
        if k == "if":
            return self.parse_if()
        if k == "while":
            self.advance()
            self.expect("(")
            cond = self.parse_expression()
            self.expect(")")
            self.loop_depth += 1
            body = self.parse_block()
            self.loop_depth -= 1
            return ("while", t.line, cond, body)
        if k == "break" or k == "continue":
            self.advance()
            if self.loop_depth == 0:
                raise ParseError(f"'{k}' outside of loop", t.line)
            self.expect(";")
            return (k, t.line)
        if k == "return":
            self.advance()
            if self.fn_depth == 0:
                raise ParseError("'return' outside of function", t.line)
            if self.check(";"):
                self.advance()
                return ("return", t.line, None)
            expr = self.parse_expression()
            self.expect(";")
            return ("return", t.line, expr)
        if k == "{":
            return self.parse_block()
        # expression statement / assignment
        expr = self.parse_expression()
        if self.check("="):
            eq = self.advance()
            if expr[0] == "ident":
                value = self.parse_expression()
                self.expect(";")
                return ("assign", eq.line, expr[2], value)
            if expr[0] == "index":
                value = self.parse_expression()
                self.expect(";")
                return ("setindex", eq.line, expr[2], expr[3], value)
            raise ParseError("invalid assignment target", eq.line)
        self.expect(";")
        return ("expr", t.line, expr)

    def parse_if(self) -> tuple:
        t = self.expect("if")
        self.expect("(")
        cond = self.parse_expression()
        self.expect(")")
        then = self.parse_block()
        otherwise = None
        if self.check("else"):
            self.advance()
            if self.check("if"):
                otherwise = self.parse_if()
            else:
                otherwise = self.parse_block()
        return ("if", t.line, cond, then, otherwise)

    def parse_fn_rest(self) -> tuple:
        self.expect("(")
        params: list[str] = []
        if not self.check(")"):
            while True:
                params.append(self.expect("ID").value)
                if self.check(","):
                    self.advance()
                    continue
                break
        self.expect(")")
        saved_loop = self.loop_depth
        self.loop_depth = 0
        self.fn_depth += 1
        body = self.parse_block()
        self.fn_depth -= 1
        self.loop_depth = saved_loop
        return params, body

    # -- expressions -----------------------------------------------------------
    def parse_expression(self) -> tuple:
        return self.parse_or()

    def _binary(self, ops: set, sub):
        left = sub()
        while self.peek().kind in ops:
            op = self.advance()
            right = sub()
            left = ("binop", op.line, op.kind, left, right)
        return left

    def parse_or(self):
        left = self.parse_and()
        while self.check("or"):
            op = self.advance()
            right = self.parse_and()
            left = ("or", op.line, left, right)
        return left

    def parse_and(self):
        left = self.parse_equality()
        while self.check("and"):
            op = self.advance()
            right = self.parse_equality()
            left = ("and", op.line, left, right)
        return left

    def parse_equality(self):
        return self._binary({"==", "!="}, self.parse_comparison)

    def parse_comparison(self):
        return self._binary({"<", "<=", ">", ">="}, self.parse_additive)

    def parse_additive(self):
        return self._binary({"+", "-"}, self.parse_multiplicative)

    def parse_multiplicative(self):
        return self._binary({"*", "/", "%"}, self.parse_unary)

    def parse_unary(self):
        t = self.peek()
        if t.kind == "-":
            self.advance()
            return ("neg", t.line, self.parse_unary())
        if t.kind == "not":
            self.advance()
            return ("not", t.line, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            t = self.peek()
            if t.kind == "(":
                self.advance()
                args = []
                if not self.check(")"):
                    while True:
                        args.append(self.parse_expression())
                        if self.check(","):
                            self.advance()
                            continue
                        break
                self.expect(")")
                expr = ("call", t.line, expr, args)
            elif t.kind == "[":
                self.advance()
                idx = self.parse_expression()
                self.expect("]")
                expr = ("index", t.line, expr, idx)
            else:
                return expr

    def parse_primary(self):
        t = self.advance()
        k = t.kind
        if k == "INT":
            return ("const", t.line, t.value)
        if k == "STR":
            return ("const", t.line, t.value)
        if k == "true":
            return ("const", t.line, True)
        if k == "false":
            return ("const", t.line, False)
        if k == "nil":
            return ("const", t.line, None)
        if k == "ID":
            return ("ident", t.line, t.value)
        if k == "(":
            e = self.parse_expression()
            self.expect(")")
            return e
        if k == "[":
            items = []
            if not self.check("]"):
                while True:
                    items.append(self.parse_expression())
                    if self.check(","):
                        self.advance()
                        continue
                    break
            self.expect("]")
            return ("list", t.line, items)
        if k == "fn":
            params, body = self.parse_fn_rest()
            return ("fn", t.line, params, body)
        found = "end of input" if k == "EOF" else repr(t.value)
        raise ParseError(f"unexpected {found}", t.line)


# ----------------------------------------------------------------------------
# Valori runtime
# ----------------------------------------------------------------------------


class Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent: Env | None = None):
        self.vars: dict = {}
        self.parent = parent


class Function:
    __slots__ = ("params", "body", "closure")

    def __init__(self, params, body, closure):
        self.params = params
        self.body = body
        self.closure = closure


class Builtin:
    __slots__ = ("name", "fn", "arity")

    def __init__(self, name, fn, arity):
        self.name = name
        self.fn = fn
        self.arity = arity  # None = variadic


class ReturnSignal:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


BREAK = object()
CONTINUE = object()


def type_name(v) -> str:
    if v is None:
        return "nil"
    t = type(v)
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is str:
        return "string"
    if t is list:
        return "list"
    return "function"


def to_str(v, top: bool = True) -> str:
    if v is None:
        return "nil"
    t = type(v)
    if t is bool:
        return "true" if v else "false"
    if t is int:
        return str(v)
    if t is str:
        return v if top else '"' + v + '"'
    if t is list:
        return "[" + ", ".join(to_str(x, False) for x in v) + "]"
    return "<function>"


def equals(a, b) -> bool:
    ta, tb = type(a), type(b)
    if ta is not tb:
        return False
    if ta is list:
        return len(a) == len(b) and all(equals(x, y) for x, y in zip(a, b))
    if ta is Function or ta is Builtin:
        return a is b
    return a == b


def _div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _mod(a: int, b: int) -> int:
    r = abs(a) % abs(b)
    return r if a >= 0 else -r


# ----------------------------------------------------------------------------
# Compilatore AST -> closure
# ----------------------------------------------------------------------------


def _type_err(op: str, a, b, line: int) -> MiniRuntimeError:
    return MiniRuntimeError(
        f"unsupported operand types for '{op}': {type_name(a)} and {type_name(b)}", line)


def compile_expr(node):
    kind = node[0]
    line = node[1]

    if kind == "const":
        v = node[2]
        return lambda env: v

    if kind == "ident":
        name = node[2]

        def ident(env):
            e = env
            while e is not None:
                vs = e.vars
                if name in vs:
                    return vs[name]
                e = e.parent
            raise MiniRuntimeError(f"undefined variable '{name}'", line)
        return ident

    if kind == "list":
        items = [compile_expr(x) for x in node[2]]
        return lambda env: [f(env) for f in items]

    if kind == "fn":
        params, body = node[2], compile_block_stmts(node[3][2])
        return lambda env: Function(params, body, env)

    if kind == "neg":
        sub = compile_expr(node[2])

        def neg(env):
            v = sub(env)
            if type(v) is not int:
                raise MiniRuntimeError(f"unary '-' requires int, got {type_name(v)}", line)
            return -v
        return neg

    if kind == "not":
        sub = compile_expr(node[2])

        def not_(env):
            v = sub(env)
            if type(v) is not bool:
                raise MiniRuntimeError(f"'not' requires bool, got {type_name(v)}", line)
            return not v
        return not_

    if kind == "and" or kind == "or":
        left, right = compile_expr(node[2]), compile_expr(node[3])
        is_and = kind == "and"

        def logical(env):
            a = left(env)
            if type(a) is not bool:
                raise MiniRuntimeError(f"'{kind}' requires bool operands, got {type_name(a)}", line)
            if is_and and not a:
                return False
            if not is_and and a:
                return True
            b = right(env)
            if type(b) is not bool:
                raise MiniRuntimeError(f"'{kind}' requires bool operands, got {type_name(b)}", line)
            return b
        return logical

    if kind == "binop":
        op, left, right = node[2], compile_expr(node[3]), compile_expr(node[4])
        return _compile_binop(op, left, right, line)

    if kind == "index":
        obj, idx = compile_expr(node[2]), compile_expr(node[3])

        def index(env):
            o = obj(env)
            i = idx(env)
            to = type(o)
            if to is not list and to is not str:
                raise MiniRuntimeError(f"cannot index {type_name(o)}", line)
            if type(i) is not int:
                raise MiniRuntimeError(f"index must be int, got {type_name(i)}", line)
            n = len(o)
            if i < -n or i >= n:
                raise MiniRuntimeError(f"index {i} out of range (length {n})", line)
            return o[i]
        return index

    if kind == "call":
        callee, args = compile_expr(node[2]), [compile_expr(a) for a in node[3]]

        def call(env):
            f = callee(env)
            argv = [a(env) for a in args]
            return call_value(f, argv, line)
        return call

    raise AssertionError(f"unknown expr node {kind}")  # pragma: no cover


def _compile_binop(op, left, right, line):
    if op == "+":
        def add(env):
            a, b = left(env), right(env)
            ta, tb = type(a), type(b)
            if ta is tb and (ta is int or ta is str or ta is list):
                return a + b
            raise _type_err(op, a, b, line)
        return add
    if op == "-":
        def sub(env):
            a, b = left(env), right(env)
            if type(a) is int and type(b) is int:
                return a - b
            raise _type_err(op, a, b, line)
        return sub
    if op == "*":
        def mul(env):
            a, b = left(env), right(env)
            if type(a) is int and type(b) is int:
                return a * b
            raise _type_err(op, a, b, line)
        return mul
    if op == "/":
        def div(env):
            a, b = left(env), right(env)
            if type(a) is int and type(b) is int:
                if b == 0:
                    raise MiniRuntimeError("division by zero", line)
                return _div(a, b)
            raise _type_err(op, a, b, line)
        return div
    if op == "%":
        def mod(env):
            a, b = left(env), right(env)
            if type(a) is int and type(b) is int:
                if b == 0:
                    raise MiniRuntimeError("modulo by zero", line)
                return _mod(a, b)
            raise _type_err(op, a, b, line)
        return mod
    if op == "==":
        return lambda env: equals(left(env), right(env))
    if op == "!=":
        return lambda env: not equals(left(env), right(env))

    import operator
    cmp = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}[op]

    def compare(env):
        a, b = left(env), right(env)
        ta, tb = type(a), type(b)
        if ta is tb and (ta is int or ta is str):
            return cmp(a, b)
        raise _type_err(op, a, b, line)
    return compare


def call_value(f, argv, line):
    tf = type(f)
    if tf is Function:
        params = f.params
        if len(argv) != len(params):
            raise MiniRuntimeError(
                f"expected {len(params)} argument(s), got {len(argv)}", line)
        env = Env(f.closure)
        env.vars = dict(zip(params, argv))
        r = f.body(Env(env))
        if type(r) is ReturnSignal:
            return r.value
        return None
    if tf is Builtin:
        if f.arity is not None and len(argv) != f.arity:
            raise MiniRuntimeError(
                f"{f.name}() expects {f.arity} argument(s), got {len(argv)}", line)
        return f.fn(argv, line)
    raise MiniRuntimeError(f"cannot call {type_name(f)}", line)


def compile_block_stmts(stmts):
    """Compila una lista di statement in una closure che esegue in un env dato (senza crearne uno)."""
    fs = [compile_stmt(s) for s in stmts]

    def run_block(env):
        for f in fs:
            r = f(env)
            if r is not None:
                return r
        return None
    return run_block


def compile_stmt(node):
    kind = node[0]
    line = node[1]

    if kind == "expr":
        e = compile_expr(node[2])

        def expr_stmt(env):
            e(env)
            return None
        return expr_stmt

    if kind == "let":
        name, e = node[2], compile_expr(node[3])

        def let(env):
            v = e(env)
            if name in env.vars:
                raise MiniRuntimeError(f"variable '{name}' already declared in this scope", line)
            env.vars[name] = v
            return None
        return let

    if kind == "assign":
        name, e = node[2], compile_expr(node[3])

        def assign(env):
            v = e(env)
            s = env
            while s is not None:
                if name in s.vars:
                    s.vars[name] = v
                    return None
                s = s.parent
            raise MiniRuntimeError(f"assignment to undeclared variable '{name}'", line)
        return assign

    if kind == "setindex":
        obj, idx, e = compile_expr(node[2]), compile_expr(node[3]), compile_expr(node[4])

        def setindex(env):
            o = obj(env)
            i = idx(env)
            v = e(env)
            if type(o) is not list:
                raise MiniRuntimeError(f"cannot assign to index of {type_name(o)}", line)
            if type(i) is not int:
                raise MiniRuntimeError(f"index must be int, got {type_name(i)}", line)
            n = len(o)
            if i < -n or i >= n:
                raise MiniRuntimeError(f"index {i} out of range (length {n})", line)
            o[i] = v
            return None
        return setindex

    if kind == "block":
        body = compile_block_stmts(node[2])
        return lambda env: body(Env(env))

    if kind == "if":
        cond = compile_expr(node[2])
        then = compile_block_stmts(node[3][2])
        otherwise = compile_stmt(node[4]) if node[4] is not None else None

        def if_(env):
            c = cond(env)
            if type(c) is not bool:
                raise MiniRuntimeError(f"condition must be bool, got {type_name(c)}", line)
            if c:
                return then(Env(env))
            if otherwise is not None:
                return otherwise(env)
            return None
        return if_

    if kind == "while":
        cond = compile_expr(node[2])
        body = compile_block_stmts(node[3][2])

        def while_(env):
            while True:
                c = cond(env)
                if type(c) is not bool:
                    raise MiniRuntimeError(f"condition must be bool, got {type_name(c)}", line)
                if not c:
                    return None
                r = body(Env(env))
                if r is not None:
                    if r is BREAK:
                        return None
                    if r is CONTINUE:
                        continue
                    return r  # ReturnSignal
        return while_

    if kind == "break":
        return lambda env: BREAK
    if kind == "continue":
        return lambda env: CONTINUE

    if kind == "return":
        if node[2] is None:
            return lambda env: ReturnSignal(None)
        e = compile_expr(node[2])
        return lambda env: ReturnSignal(e(env))

    raise AssertionError(f"unknown stmt node {kind}")  # pragma: no cover


# ----------------------------------------------------------------------------
# Built-in
# ----------------------------------------------------------------------------

_INT_RE = re.compile(r"-?[0-9]+\Z")


def make_globals(out: list[str]) -> Env:
    def b_print(args, line):
        out.append(" ".join(to_str(a) for a in args) + "\n")
        return None

    def b_len(args, line):
        (x,) = args
        if type(x) is str or type(x) is list:
            return len(x)
        raise MiniRuntimeError(f"len() requires string or list, got {type_name(x)}", line)

    def b_push(args, line):
        xs, v = args
        if type(xs) is not list:
            raise MiniRuntimeError(f"push() requires list, got {type_name(xs)}", line)
        xs.append(v)
        return None

    def b_pop(args, line):
        (xs,) = args
        if type(xs) is not list:
            raise MiniRuntimeError(f"pop() requires list, got {type_name(xs)}", line)
        if not xs:
            raise MiniRuntimeError("pop() from empty list", line)
        return xs.pop()

    def b_str(args, line):
        return to_str(args[0])

    def b_int(args, line):
        (x,) = args
        if type(x) is int:
            return x
        if type(x) is str and _INT_RE.match(x):
            return int(x)
        raise MiniRuntimeError(f"int() cannot convert {to_str(x) if type(x) is not str else repr(x)}", line)

    def b_type(args, line):
        return type_name(args[0])

    def b_range(args, line):
        (n,) = args
        if type(n) is not int:
            raise MiniRuntimeError(f"range() requires int, got {type_name(n)}", line)
        return list(range(n)) if n > 0 else []

    g = Env()
    for name, fn, arity in (
        ("print", b_print, None), ("len", b_len, 1), ("push", b_push, 2), ("pop", b_pop, 1),
        ("str", b_str, 1), ("int", b_int, 1), ("type", b_type, 1), ("range", b_range, 1),
    ):
        g.vars[name] = Builtin(name, fn, arity)
    return g


# ----------------------------------------------------------------------------
# API pubblica
# ----------------------------------------------------------------------------


def run(source: str) -> str:
    out: list[str] = []
    try:
        program = compile_block_stmts(Parser(tokenize(source)).parse_program())
    except MiniLangError as e:
        e.output = ""
        raise
    env = make_globals(out)
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, 20000))
    try:
        program(env)
    except MiniLangError as e:
        e.output = "".join(out)
        raise
    except RecursionError:
        err = MiniRuntimeError("maximum recursion depth exceeded", 0)
        err.output = "".join(out)
        raise err from None
    finally:
        sys.setrecursionlimit(old_limit)
    return "".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python minilang.py <file>\n")
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            source = fh.read()
    except OSError as e:
        sys.stderr.write(f"error: cannot read {argv[1]}: {e}\n")
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        output = run(source)
    except ParseError as e:
        sys.stdout.write(e.output)
        sys.stdout.flush()
        sys.stderr.write(f"ParseError: line {e.line}: {e.message}\n")
        return 1
    except MiniRuntimeError as e:
        sys.stdout.write(e.output)
        sys.stdout.flush()
        sys.stderr.write(f"RuntimeError: line {e.line}: {e.message}\n")
        return 1
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
