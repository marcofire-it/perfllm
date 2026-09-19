"""MiniLang: lexer, parser and tree-walking interpreter for a small imperative
language with closures, lists and built-ins.

Standard library only.  Public API:

    from minilang import run, MiniLangError, ParseError, MiniRuntimeError

CLI:
    python minilang.py <file>
"""

import sys

__all__ = ["MiniLangError", "ParseError", "MiniRuntimeError", "run", "main"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MiniLangError(Exception):
    """Base class for all MiniLang errors.

    Attributes:
        line:   1-based line where the error occurred.
        output: output produced before the error (string).
    """

    def __init__(self, line, message):
        super().__init__(message)
        self.line = line
        self.message = message
        self.output = ""

    def __str__(self):
        return self.message


class ParseError(MiniLangError):
    """Lexical or syntactic error."""


class MiniRuntimeError(MiniLangError):
    """Runtime error (types, names, indexes, arity, division by zero, ...)."""


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

_KEYWORDS = {
    "let", "fn", "return", "if", "else", "while", "break", "continue",
    "and", "or", "not", "true", "false", "nil",
}
_TWO_CHAR_OPS = ("==", "!=", "<=", ">=")
_PUNCT = set("+-*/%(){}[],;=<>")
_DIGITS = set("0123456789")
_LETTERS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


class _Lexer:
    def __init__(self, src):
        self.src = src
        self.n = len(src)
        self.pos = 0
        self.line = 1
        self.tokens = []

    def _err(self, msg, line=None):
        raise ParseError(line if line is not None else self.line, msg)

    def tokenize(self):
        src, n = self.src, self.n
        while self.pos < n:
            c = src[self.pos]
            if c == "\n":
                self.line += 1
                self.pos += 1
                continue
            if c in " \t\r":
                self.pos += 1
                continue
            if c == "/" and self.pos + 1 < n and src[self.pos + 1] == "/":
                while self.pos < n and src[self.pos] != "\n":
                    self.pos += 1
                continue
            line = self.line
            if c in _DIGITS:
                start = self.pos
                while self.pos < n and src[self.pos] in _DIGITS:
                    self.pos += 1
                self.tokens.append(("int", int(src[start:self.pos]), line))
                continue
            if c == '"':
                self.pos += 1
                chars = []
                while True:
                    if self.pos >= n or src[self.pos] == "\n":
                        self._err("unterminated string", line)
                    ch = src[self.pos]
                    if ch == '"':
                        self.pos += 1
                        break
                    if ch == "\\":
                        self.pos += 1
                        if self.pos >= n or src[self.pos] == "\n":
                            self._err("unterminated escape in string", line)
                        esc = src[self.pos]
                        if esc not in _ESCAPES:
                            self._err("invalid escape '\\%s'" % esc, line)
                        chars.append(_ESCAPES[esc])
                        self.pos += 1
                    else:
                        chars.append(ch)
                        self.pos += 1
                self.tokens.append(("str", "".join(chars), line))
                continue
            if c in _LETTERS or c == "_":
                start = self.pos
                while (
                    self.pos < n
                    and (src[self.pos] in _LETTERS or src[self.pos] in _DIGITS or src[self.pos] == "_")
                ):
                    self.pos += 1
                word = src[start:self.pos]
                if word in _KEYWORDS:
                    self.tokens.append((word, word, line))
                else:
                    self.tokens.append(("ident", word, line))
                continue
            if self.pos + 1 < n and src[self.pos:self.pos + 2] in _TWO_CHAR_OPS:
                two = src[self.pos:self.pos + 2]
                self.tokens.append((two, two, line))
                self.pos += 2
                continue
            if c in _PUNCT:
                self.tokens.append((c, c, line))
                self.pos += 1
                continue
            self._err("invalid character %r" % c, line)
        self.tokens.append(("eof", None, self.line))
        return self.tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
#
# AST nodes are tuples: (tag, ...); the line number is always the last element.
#
# Statements:
#   ('let', name, expr, line)
#   ('assign', name, expr, line)
#   ('indexassign', name, idx, expr, line)
#   ('exprstmt', expr, line)
#   ('if', cond, then_body, else_body_or_None, line)
#   ('while', cond, body, line)
#   ('break', line)  ('continue', line)
#   ('return', expr_or_None, line)
#   ('fndecl', name, params, body, line)
#   ('block', stmts, line)
#
# Expressions:
#   ('num', value, line)  ('str', value, line)  ('bool', value, line)
#   ('nil', line)  ('ident', name, line)
#   ('list', [expr, ...], line)
#   ('fnlit', params, body, line)
#   ('binop', op, left, right, line)
#   ('unary', op, expr, line)
#   ('call', func, [args], line)
#   ('index', obj, idx, line)


class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # -- token helpers ------------------------------------------------------
    def peek(self, off=0):
        return self.toks[self.i + off]

    def advance(self):
        t = self.toks[self.i]
        if t[0] != "eof":
            self.i += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        if t[0] != kind:
            return False
        return value is None or t[1] == value

    def expect(self, kind, what=None):
        t = self.peek()
        if t[0] != kind:
            self._err(what or "expected %r" % kind)
        return self.advance()

    def _err(self, msg):
        raise ParseError(self.peek()[2], msg)

    # -- grammar ------------------------------------------------------------
    def parse(self):
        stmts = []
        while not self.at("eof"):
            stmts.append(self.statement(0, 0))
        return stmts

    def statement(self, wd, fd):
        t = self.peek()
        kind, line = t[0], t[2]
        if kind == "let":
            self.advance()
            name = self.expect("ident", "expected identifier after 'let'")[1]
            self.expect("=", "expected '=' in 'let' declaration")
            e = self.expr()
            self.expect(";", "expected ';' after 'let' statement")
            return ("let", name, e, line)
        if kind == "if":
            self.advance()
            self.expect("(", "expected '(' after 'if'")
            cond = self.expr()
            self.expect(")", "expected ')' after condition")
            then = self.block(wd, fd)
            els = None
            if self.at("else"):
                self.advance()
                if self.at("if"):
                    n = self.statement(wd, fd)
                    if n[0] != "if":
                        self._err("'else if' must be followed by an 'if'")
                    els = n
                else:
                    els = self.block(wd, fd)
            return ("if", cond, then, els, line)
        if kind == "while":
            self.advance()
            self.expect("(", "expected '(' after 'while'")
            cond = self.expr()
            self.expect(")", "expected ')' after condition")
            body = self.block(wd + 1, fd)
            return ("while", cond, body, line)
        if kind == "break":
            if wd == 0:
                self._err("'break' outside of a 'while' loop")
            self.advance()
            self.expect(";", "expected ';' after 'break'")
            return ("break", line)
        if kind == "continue":
            if wd == 0:
                self._err("'continue' outside of a 'while' loop")
            self.advance()
            self.expect(";", "expected ';' after 'continue'")
            return ("continue", line)
        if kind == "return":
            if fd == 0:
                self._err("'return' outside of a function")
            self.advance()
            if self.at(";"):
                self.advance()
                return ("return", None, line)
            e = self.expr()
            self.expect(";", "expected ';' after 'return'")
            return ("return", e, line)
        if kind == "fn" and self.peek(1)[0] == "ident":
            self.advance()
            name = self.advance()[1]
            params = self.params()
            body = self.block(wd, fd + 1)
            return ("fndecl", name, params, body, line)
        if kind == "{":
            return self.block(wd, fd)
        if kind == "ident":
            nxt = self.peek(1)[0]
            if nxt == "=":
                name = self.advance()[1]
                self.advance()
                e = self.expr()
                self.expect(";", "expected ';' after assignment")
                return ("assign", name, e, line)
            if nxt == "[":
                name = self.advance()[1]
                idxs = []
                while self.at("["):
                    self.advance()
                    idxs.append(self.expr())
                    self.expect("]", "expected ']' after index")
                self.expect("=", "expected '=' after 'name[index]'")
                e = self.expr()
                self.expect(";", "expected ';' after index assignment")
                return ("indexassign", name, idxs, e, line)
        if kind == "eof":
            self._err("unexpected end of input")
        e = self.expr()
        self.expect(";", "expected ';' after expression statement")
        return ("exprstmt", e, line)

    def block(self, wd, fd):
        line = self.expect("{", "expected '{' to open block")[2]
        stmts = []
        while not self.at("}"):
            if self.at("eof"):
                self._err("unterminated block, expected '}'")
            stmts.append(self.statement(wd, fd))
        self.advance()  # '}'
        return ("block", stmts, line)

    def params(self):
        self.expect("(", "expected '(' after function name")
        ps = []
        if not self.at(")"):
            while True:
                p = self.expect("ident", "expected parameter name")[1]
                ps.append(p)
                if self.at(","):
                    self.advance()
                    continue
                break
        self.expect(")", "expected ')' after parameters")
        return ps

    # -- expressions ---------------------------------------------------------
    def expr(self):
        return self.or_expr()

    def or_expr(self):
        node = self.and_expr()
        while self.at("or"):
            op_line = self.advance()[2]
            node = ("binop", "or", node, self.and_expr(), op_line)
        return node

    def and_expr(self):
        node = self.eq_expr()
        while self.at("and"):
            op_line = self.advance()[2]
            node = ("binop", "and", node, self.eq_expr(), op_line)
        return node

    def eq_expr(self):
        node = self.cmp_expr()
        while self.at("==") or self.at("!="):
            t = self.advance()
            node = ("binop", t[0], node, self.cmp_expr(), t[2])
        return node

    def cmp_expr(self):
        node = self.add_expr()
        while self.at("<") or self.at("<=") or self.at(">") or self.at(">="):
            t = self.advance()
            node = ("binop", t[0], node, self.add_expr(), t[2])
        return node

    def add_expr(self):
        node = self.mul_expr()
        while self.at("+") or self.at("-"):
            t = self.advance()
            node = ("binop", t[0], node, self.mul_expr(), t[2])
        return node

    def mul_expr(self):
        node = self.unary()
        while self.at("*") or self.at("/") or self.at("%"):
            t = self.advance()
            node = ("binop", t[0], node, self.unary(), t[2])
        return node

    def unary(self):
        if self.at("-") or self.at("not"):
            op = self.advance()[0]
            line = self.peek()[2]
            return ("unary", op, self.unary(), line)
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while True:
            if self.at("("):
                self.advance()
                args = []
                if not self.at(")"):
                    while True:
                        args.append(self.expr())
                        if self.at(","):
                            self.advance()
                            continue
                        break
                self.expect(")", "expected ')' after arguments")
                node = ("call", node, args, self.peek()[2])
            elif self.at("["):
                self.advance()
                idx = self.expr()
                self.expect("]", "expected ']' after index")
                node = ("index", node, idx, self.peek()[2])
            else:
                break
        return node

    def primary(self):
        t = self.peek()
        kind, value, line = t
        if kind == "int":
            self.advance()
            return ("num", value, line)
        if kind == "str":
            self.advance()
            return ("str", value, line)
        if kind == "true" or kind == "false":
            self.advance()
            return ("bool", kind == "true", line)
        if kind == "nil":
            self.advance()
            return ("nil", line)
        if kind == "ident":
            self.advance()
            return ("ident", value, line)
        if kind == "(":
            self.advance()
            e = self.expr()
            self.expect(")", "expected ')' after expression")
            return e
        if kind == "[":
            self.advance()
            items = []
            if not self.at("]"):
                while True:
                    items.append(self.expr())
                    if self.at(","):
                        self.advance()
                        continue
                    break
            self.expect("]", "expected ']' after list literal")
            return ("list", items, line)
        if kind == "fn":
            self.advance()
            params = self.params()
            body = self.block(0, 1)
            return ("fnlit", params, body, line)
        self._err("unexpected token %r" % (value if value is not None else kind))


# ---------------------------------------------------------------------------
# Values / runtime
# ---------------------------------------------------------------------------


class _Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent):
        self.vars = {}
        self.parent = parent


class _Function:
    __slots__ = ("params", "body", "closure", "line")

    def __init__(self, params, body, closure, line):
        self.params = params
        self.body = body
        self.closure = closure
        self.line = line


class _Builtin:
    __slots__ = ("name", "func")

    def __init__(self, name, func):
        self.name = name
        self.func = func


class _Break(Exception):
    __slots__ = ()


class _Continue(Exception):
    __slots__ = ()


class _Return(Exception):
    __slots__ = ("value",)

    def __init__(self, value):
        super().__init__(value)
        self.value = value


def _is_int(v):
    return type(v) is int


def _is_bool(v):
    return type(v) is bool


def _deep_eq(a, b):
    if _is_bool(a) or _is_bool(b):
        return _is_bool(a) and _is_bool(b) and a == b
    if _is_int(a) or _is_int(b):
        return _is_int(a) and _is_int(b) and a == b
    if type(a) is str or type(b) is str:
        return type(a) is str and type(b) is str and a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, _Function) or isinstance(b, _Function):
        return a is b
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if not _deep_eq(x, y):
                return False
        return True
    return a is b


def _to_str_top(v):
    """Textual form of a value at top level (print argument / str())."""
    if _is_bool(v):
        return "true" if v else "false"
    if _is_int(v):
        return str(v)
    if type(v) is str:
        return v
    if v is None:
        return "nil"
    if isinstance(v, _Function) or isinstance(v, _Builtin):
        return "<function>"
    return _to_str_list(v)


def _to_str_list(v):
    return "[" + ", ".join(_to_str_elem(x) for x in v) + "]"


def _to_str_elem(v):
    if type(v) is str:
        return '"' + v + '"'
    return _to_str_top(v)


def _trunc_div(a, b):
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------


class _Interpreter:
    def __init__(self):
        self.output = []
        self.globals = _Env(None)
        self._init_builtins()

    # -- built-ins -----------------------------------------------------------
    def _init_builtins(self):
        g = self.globals

        def b_print(interp, args, line):
            interp.output.append(" ".join(_to_str_top(a) for a in args) + "\n")
            return None

        def b_len(interp, args, line):
            a = args[0]
            if type(a) is str or isinstance(a, list):
                return len(a)
            raise MiniRuntimeError(line, "len() expects a string or a list")

        def b_push(interp, args, line):
            a = args[0]
            if not isinstance(a, list):
                raise MiniRuntimeError(line, "push() expects a list")
            a.append(args[1])
            return None

        def b_pop(interp, args, line):
            a = args[0]
            if not isinstance(a, list):
                raise MiniRuntimeError(line, "pop() expects a list")
            if not a:
                raise MiniRuntimeError(line, "pop() on an empty list")
            return a.pop()

        def b_str(interp, args, line):
            return _to_str_top(args[0])

        def b_int(interp, args, line):
            a = args[0]
            if _is_int(a):
                return a
            if type(a) is not str:
                raise MiniRuntimeError(line, "int() expects a string or an int")
            s = a
            body = s[1:] if s.startswith("-") else s
            if not body or any(c not in _DIGITS for c in body):
                raise MiniRuntimeError(line, "int(): invalid string %r" % s)
            return int(s)

        def b_type(interp, args, line):
            a = args[0]
            if _is_bool(a):
                return "bool"
            if _is_int(a):
                return "int"
            if type(a) is str:
                return "string"
            if isinstance(a, list):
                return "list"
            if isinstance(a, _Function) or isinstance(a, _Builtin):
                return "function"
            return "nil"

        def b_range(interp, args, line):
            a = args[0]
            if not _is_int(a):
                raise MiniRuntimeError(line, "range() expects an int")
            if a < 0:
                return []
            return list(range(a))

        for name, func in (
            ("print", b_print),
            ("len", b_len),
            ("push", b_push),
            ("pop", b_pop),
            ("str", b_str),
            ("int", b_int),
            ("type", b_type),
            ("range", b_range),
        ):
            g.vars[name] = _Builtin(name, func)

    # -- helpers --------------------------------------------------------------
    def _emit(self, s):
        self.output.append(s)

    def _resolve(self, name, env, line):
        e = env
        while e is not None:
            v = e.vars.get(name)
            if v is not None:
                return v
            e = e.parent
        raise MiniRuntimeError(
            line, "use of undeclared variable '%s'" % name
        )

    def _lookup(self, name, env, line):
        e = env
        while e is not None:
            if name in e.vars:
                return e
            e = e.parent
        raise MiniRuntimeError(
            line, "assignment to undeclared variable '%s'" % name
        )

    def _require_int(self, v, line, what):
        if not _is_int(v):
            raise MiniRuntimeError(line, "%s: operand must be an int" % what)

    # -- statements ------------------------------------------------------------
    def run_program(self, stmts):
        env = self.globals
        for s in stmts:
            self.stmt(s, env)

    def stmt(self, s, env):
        tag = s[0]
        if tag == "let":
            _, name, e, line = s
            if name in env.vars:
                raise MiniRuntimeError(
                    line, "redeclaration of '%s' in the same scope" % name
                )
            env.vars[name] = self.expr(e, env)
        elif tag == "fndecl":
            _, name, params, body, line = s
            if name in env.vars:
                raise MiniRuntimeError(
                    line, "redeclaration of '%s' in the same scope" % name
                )
            env.vars[name] = _Function(params, body, env, line)
        elif tag == "assign":
            _, name, e, line = s
            self._lookup(name, env, line).vars[name] = self.expr(e, env)
        elif tag == "indexassign":
            _, name, idxs, e, line = s
            obj = self._resolve(name, env, line)
            vals = []
            for idx in idxs:
                i = self.expr(idx, env)
                if not _is_int(i):
                    raise MiniRuntimeError(line, "index must be an int")
                vals.append(i)
            for i in vals[:-1]:
                if isinstance(obj, list):
                    i2 = i + len(obj) if i < 0 else i
                    if i2 < 0 or i2 >= len(obj):
                        raise MiniRuntimeError(line, "index out of range")
                    obj = obj[i2]
                elif type(obj) is str:
                    raise MiniRuntimeError(line, "cannot assign into a string")
                else:
                    raise MiniRuntimeError(
                        line, "indexing requires a list or a string"
                    )
            i = vals[-1]
            if not isinstance(obj, list):
                raise MiniRuntimeError(line, "index assignment requires a list")
            i2 = i + len(obj) if i < 0 else i
            if i2 < 0 or i2 >= len(obj):
                raise MiniRuntimeError(line, "index out of range")
            obj[i2] = self.expr(e, env)
        elif tag == "exprstmt":
            self.expr(s[1], env)
        elif tag == "if":
            _, cond, then, els, line = s
            c = self.expr(cond, env)
            if not _is_bool(c):
                raise MiniRuntimeError(line, "if: condition must be a bool")
            if c:
                self.stmt(then, env)  # then is a ('block', ...) node
            elif els is not None:
                self.stmt(els, env)
        elif tag == "while":
            _, cond, body, line = s
            while True:
                c = self.expr(cond, env)
                if not _is_bool(c):
                    raise MiniRuntimeError(line, "while: condition must be a bool")
                if not c:
                    break
                try:
                    self.stmt(body, env)  # body is a ('block', ...) node
                except _Break:
                    break
                except _Continue:
                    continue
        elif tag == "break":
            raise _Break()
        elif tag == "continue":
            raise _Continue()
        elif tag == "return":
            e = s[1]
            raise _Return(self.expr(e, env) if e is not None else None)
        elif tag == "block":
            self.run_block(s[1], _Env(env))
        else:  # pragma: no cover - defensive
            raise MiniRuntimeError(s[-1], "unknown statement %r" % tag)

    def run_block(self, stmts, env):
        for s in stmts:
            self.stmt(s, env)

    # -- expressions -------------------------------------------------------------
    def expr(self, n, env):
        tag = n[0]
        if tag == "num" or tag == "str" or tag == "bool":
            return n[1]
        if tag == "nil":
            return None
        if tag == "ident":
            return self._resolve(n[1], env, n[2])
        if tag == "list":
            return [self.expr(x, env) for x in n[1]]
        if tag == "fnlit":
            return _Function(n[1], n[2], env, n[3])
        if tag == "unary":
            _, op, e, line = n
            v = self.expr(e, env)
            if op == "-":
                self._require_int(v, line, "unary '-'")
                return -v
            if not _is_bool(v):
                raise MiniRuntimeError(line, "'not' expects a bool")
            return not v
        if tag == "binop":
            return self.binop(n, env)
        if tag == "index":
            _, obj, idx, line = n
            o = self.expr(obj, env)
            i = self.expr(idx, env)
            if not _is_int(i):
                raise MiniRuntimeError(line, "index must be an int")
            if _is_int(o) or _is_bool(o) or o is None:
                raise MiniRuntimeError(line, "indexing requires a list or a string")
            if type(o) is str:
                i2 = i + len(o) if i < 0 else i
                if i2 < 0 or i2 >= len(o):
                    raise MiniRuntimeError(line, "index out of range")
                return o[i2]
            if isinstance(o, list):
                i2 = i + len(o) if i < 0 else i
                if i2 < 0 or i2 >= len(o):
                    raise MiniRuntimeError(line, "index out of range")
                return o[i2]
            raise MiniRuntimeError(line, "indexing requires a list or a string")
        if tag == "call":
            return self.call(n, env)
        raise MiniRuntimeError(n[-1], "unknown expression %r" % tag)  # pragma: no cover

    def binop(self, n, env):
        _, op, le, re, line = n
        if op == "and":
            l = self.expr(le, env)
            if not _is_bool(l):
                raise MiniRuntimeError(line, "'and' expects bool operands")
            if not l:
                return False
            r = self.expr(re, env)
            if not _is_bool(r):
                raise MiniRuntimeError(line, "'and' expects bool operands")
            return r
        if op == "or":
            l = self.expr(le, env)
            if not _is_bool(l):
                raise MiniRuntimeError(line, "'or' expects bool operands")
            if l:
                return True
            r = self.expr(re, env)
            if not _is_bool(r):
                raise MiniRuntimeError(line, "'or' expects bool operands")
            return r
        a = self.expr(le, env)
        b = self.expr(re, env)
        if op == "+":
            if _is_int(a) and _is_int(b):
                return a + b
            if type(a) is str and type(b) is str:
                return a + b
            if isinstance(a, list) and isinstance(b, list):
                return a + b
            raise MiniRuntimeError(line, "'+' has incompatible operands")
        if op == "-":
            self._require_int(a, line, "'-'")
            self._require_int(b, line, "'-'")
            return a - b
        if op == "*":
            self._require_int(a, line, "'*'")
            self._require_int(b, line, "'*'")
            return a * b
        if op == "/":
            self._require_int(a, line, "'/'")
            self._require_int(b, line, "'/'")
            if b == 0:
                raise MiniRuntimeError(line, "division by zero")
            return _trunc_div(a, b)
        if op == "%":
            self._require_int(a, line, "'%'")
            self._require_int(b, line, "'%'")
            if b == 0:
                raise MiniRuntimeError(line, "modulo by zero")
            return a - _trunc_div(a, b) * b
        if op == "==":
            return _deep_eq(a, b)
        if op == "!=":
            return not _deep_eq(a, b)
        if op in ("<", "<=", ">", ">="):
            if _is_int(a) and _is_int(b):
                pass
            elif type(a) is str and type(b) is str:
                pass
            else:
                raise MiniRuntimeError(line, "comparison has incompatible operands")
            if op == "<":
                return a < b
            if op == "<=":
                return a <= b
            if op == ">":
                return a > b
            return a >= b
        raise MiniRuntimeError(line, "unknown operator %r" % op)  # pragma: no cover

    def call(self, n, env):
        _, func, args, line = n
        f = self.expr(func, env)
        if isinstance(f, _Builtin):
            vals = [self.expr(a, env) for a in args]
            return f.func(self, vals, line)
        if not isinstance(f, _Function):
            raise MiniRuntimeError(line, "attempt to call a non-function")
        if len(args) != len(f.params):
            raise MiniRuntimeError(
                line,
                "function expects %d argument(s), got %d"
                % (len(f.params), len(args)),
            )
        cenv = _Env(f.closure)
        for name, a in zip(f.params, args):
            if name in cenv.vars:
                raise MiniRuntimeError(line, "duplicate parameter '%s'" % name)
            cenv.vars[name] = self.expr(a, env)
        try:
            self.stmt(f.body, cenv)  # f.body is a ('block', ...) node
        except _Return as r:
            return r.value
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MIN_RECURSION_LIMIT = 20000


def run(source):
    """Run a MiniLang program; return everything printed to stdout.

    Raises ParseError or MiniRuntimeError; the output produced before the
    error is available in the exception's `output` attribute.
    """
    try:
        if sys.getrecursionlimit() < _MIN_RECURSION_LIMIT:
            sys.setrecursionlimit(_MIN_RECURSION_LIMIT)
        interp = _Interpreter()
        tokens = _Lexer(source).tokenize()
        stmts = _Parser(tokens).parse()
        interp.run_program(stmts)
        return "".join(interp.output)
    except MiniLangError as err:
        err.output = "".join(interp.output)
        raise


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        sys.stderr.write("usage: python minilang.py <file>\n")
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        sys.stderr.write("error: cannot read '%s': %s\n" % (path, e))
        return 2
    try:
        out = run(source)
    except (ParseError, MiniRuntimeError) as err:
        sys.stdout.write(err.output)
        sys.stdout.flush()
        name = "ParseError" if isinstance(err, ParseError) else "RuntimeError"
        sys.stderr.write("%s: line %d: %s\n" % (name, err.line, err.message))
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
