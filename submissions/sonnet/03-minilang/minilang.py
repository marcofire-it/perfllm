#!/usr/bin/env python3
"""minilang.py -- lexer, parser e interprete per il linguaggio MiniLang.

Sola libreria standard. Nessun eval/exec. Importabile senza effetti collaterali.
"""

import re
import sys


# ---------------------------------------------------------------------------
# Eccezioni pubbliche
# ---------------------------------------------------------------------------

class MiniLangError(Exception):
    """Base per gli errori del linguaggio. `line` e' 1-based, `output` e'
    l'output prodotto prima dell'errore (riempito da run())."""

    def __init__(self, message, line):
        super().__init__(message)
        self.message = message
        self.line = line
        self.output = ""

    def __str__(self):
        return self.message


class ParseError(MiniLangError):
    """Errori lessicali e sintattici."""


class MiniRuntimeError(MiniLangError):
    """Errori a runtime (tipi, nomi, indici, arita', divisione per zero, ...)."""


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

KEYWORDS = {
    "let", "fn", "return", "if", "else", "while", "break", "continue",
    "and", "or", "not", "true", "false", "nil",
}


class Token:
    __slots__ = ("type", "value", "line")

    def __init__(self, type_, value, line):
        self.type = type_
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r}, {self.line})"


_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


def tokenize(source):
    tokens = []
    i = 0
    n = len(source)
    line = 1

    while i < n:
        c = source[i]

        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue

        if c.isdigit():
            start = i
            while i < n and source[i].isdigit():
                i += 1
            tokens.append(Token("INT", int(source[start:i]), line))
            continue

        if c == '"':
            start_line = line
            i += 1
            buf = []
            closed = False
            while i < n:
                ch = source[i]
                if ch == '"':
                    i += 1
                    closed = True
                    break
                if ch == "\n":
                    break
                if ch == "\\":
                    if i + 1 >= n or source[i + 1] == "\n":
                        raise ParseError("stringa non terminata", start_line)
                    esc = source[i + 1]
                    if esc not in _ESCAPES:
                        raise ParseError(
                            f"sequenza di escape non valida '\\{esc}'", line)
                    buf.append(_ESCAPES[esc])
                    i += 2
                    continue
                buf.append(ch)
                i += 1
            if not closed:
                raise ParseError("stringa non terminata", start_line)
            tokens.append(Token("STRING", "".join(buf), start_line))
            continue

        if c.isalpha() or c == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text = source[start:i]
            if text in KEYWORDS:
                tokens.append(Token("KW", text, line))
            else:
                tokens.append(Token("IDENT", text, line))
            continue

        two = source[i:i + 2]
        if two in ("==", "!=", "<=", ">="):
            tokens.append(Token(two, two, line))
            i += 2
            continue

        if c in "(){}[],;=<>+-*/%":
            tokens.append(Token(c, c, line))
            i += 1
            continue

        raise ParseError(f"carattere non valido '{c}'", line)

    tokens.append(Token("EOF", None, line))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

class Node:
    __slots__ = ("line",)


class IntLit(Node):
    __slots__ = ("value",)

    def __init__(self, value, line):
        self.value = value
        self.line = line


class StringLit(Node):
    __slots__ = ("value",)

    def __init__(self, value, line):
        self.value = value
        self.line = line


class BoolLit(Node):
    __slots__ = ("value",)

    def __init__(self, value, line):
        self.value = value
        self.line = line


class NilLit(Node):
    def __init__(self, line):
        self.line = line


class ListLit(Node):
    __slots__ = ("elements",)

    def __init__(self, elements, line):
        self.elements = elements
        self.line = line


class FnLit(Node):
    __slots__ = ("params", "body")

    def __init__(self, params, body, line):
        self.params = params
        self.body = body
        self.line = line


class Name(Node):
    __slots__ = ("name",)

    def __init__(self, name, line):
        self.name = name
        self.line = line


class Unary(Node):
    __slots__ = ("op", "operand")

    def __init__(self, op, operand, line):
        self.op = op
        self.operand = operand
        self.line = line


class Binary(Node):
    __slots__ = ("op", "left", "right")

    def __init__(self, op, left, right, line):
        self.op = op
        self.left = left
        self.right = right
        self.line = line


class Logical(Node):
    __slots__ = ("op", "left", "right")

    def __init__(self, op, left, right, line):
        self.op = op
        self.left = left
        self.right = right
        self.line = line


class Call(Node):
    __slots__ = ("callee", "args")

    def __init__(self, callee, args, line):
        self.callee = callee
        self.args = args
        self.line = line


class Index(Node):
    __slots__ = ("obj", "index")

    def __init__(self, obj, index, line):
        self.obj = obj
        self.index = index
        self.line = line


# Statements

class LetStmt(Node):
    __slots__ = ("name", "expr")

    def __init__(self, name, expr, line):
        self.name = name
        self.expr = expr
        self.line = line


class AssignStmt(Node):
    __slots__ = ("target", "value")

    def __init__(self, target, value, line):
        self.target = target
        self.value = value
        self.line = line


class ExprStmt(Node):
    __slots__ = ("expr",)

    def __init__(self, expr, line):
        self.expr = expr
        self.line = line


class BlockStmt(Node):
    __slots__ = ("stmts",)

    def __init__(self, stmts, line):
        self.stmts = stmts
        self.line = line


class IfStmt(Node):
    __slots__ = ("cond", "then_body", "else_part")

    def __init__(self, cond, then_body, else_part, line):
        self.cond = cond
        self.then_body = then_body
        self.else_part = else_part  # None | list[stmt] | IfStmt
        self.line = line


class WhileStmt(Node):
    __slots__ = ("cond", "body")

    def __init__(self, cond, body, line):
        self.cond = cond
        self.body = body
        self.line = line


class BreakStmt(Node):
    def __init__(self, line):
        self.line = line


class ContinueStmt(Node):
    def __init__(self, line):
        self.line = line


class ReturnStmt(Node):
    __slots__ = ("expr",)

    def __init__(self, expr, line):
        self.expr = expr
        self.line = line


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.loop_depth = 0
        self.func_depth = 0

    def peek(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def at(self, type_, value=None):
        tok = self.peek()
        return tok.type == type_ and (value is None or tok.value == value)

    def match(self, type_, value=None):
        if self.at(type_, value):
            return self.advance()
        return None

    def expect(self, type_, value=None, msg=None):
        if not self.at(type_, value):
            tok = self.peek()
            got = tok.value if tok.value is not None else tok.type
            default_msg = f"atteso '{value or type_}', trovato '{got}'"
            raise ParseError(msg or default_msg, tok.line)
        return self.advance()

    def error(self, msg, line=None):
        raise ParseError(msg, line if line is not None else self.peek().line)

    # -- program -----------------------------------------------------

    def parse_program(self):
        stmts = []
        while not self.at("EOF"):
            stmts.append(self.statement())
        return stmts

    def parse_block(self):
        self.expect("{", msg="atteso '{'")
        stmts = []
        while not self.at("}") and not self.at("EOF"):
            stmts.append(self.statement())
        if not self.at("}"):
            self.error("atteso '}'", self.peek().line)
        self.advance()
        return stmts

    # -- statements ----------------------------------------------------

    def statement(self):
        tok = self.peek()

        if tok.type == "KW":
            if tok.value == "let":
                return self.parse_let()
            if tok.value == "fn":
                return self.parse_fn_decl()
            if tok.value == "if":
                return self.parse_if()
            if tok.value == "while":
                return self.parse_while()
            if tok.value == "break":
                if self.loop_depth == 0:
                    self.error("'break' fuori da un while", tok.line)
                self.advance()
                self.expect(";", msg="atteso ';' dopo 'break'")
                return BreakStmt(tok.line)
            if tok.value == "continue":
                if self.loop_depth == 0:
                    self.error("'continue' fuori da un while", tok.line)
                self.advance()
                self.expect(";", msg="atteso ';' dopo 'continue'")
                return ContinueStmt(tok.line)
            if tok.value == "return":
                if self.func_depth == 0:
                    self.error("'return' fuori da una funzione", tok.line)
                self.advance()
                if self.at(";"):
                    self.advance()
                    return ReturnStmt(None, tok.line)
                expr = self.parse_expression()
                self.expect(";", msg="atteso ';' dopo 'return'")
                return ReturnStmt(expr, tok.line)

        if tok.type == "{":
            line = tok.line
            stmts = self.parse_block()
            return BlockStmt(stmts, line)

        return self.parse_expr_or_assign()

    def parse_let(self):
        line = self.advance().line  # 'let'
        name_tok = self.expect("IDENT", msg="atteso un identificatore dopo 'let'")
        if not self.at("="):
            self.error("dichiarazione 'let' senza inizializzatore", self.peek().line)
        self.advance()
        expr = self.parse_expression()
        self.expect(";", msg="atteso ';' dopo la dichiarazione")
        return LetStmt(name_tok.value, expr, line)

    def parse_fn_decl(self):
        line = self.advance().line  # 'fn'
        name_tok = self.expect("IDENT", msg="atteso un nome di funzione dopo 'fn'")
        self.expect("(", msg="atteso '(' dopo il nome della funzione")
        params = self.parse_param_list()
        self.expect(")", msg="atteso ')' dopo i parametri")
        saved_loop = self.loop_depth
        self.loop_depth = 0
        self.func_depth += 1
        body = self.parse_block()
        self.func_depth -= 1
        self.loop_depth = saved_loop
        fnlit = FnLit(params, body, line)
        return LetStmt(name_tok.value, fnlit, line)

    def parse_param_list(self):
        params = []
        if self.at(")"):
            return params
        tok = self.expect("IDENT", msg="atteso un identificatore come parametro")
        params.append(tok.value)
        while self.match(","):
            tok = self.expect("IDENT", msg="atteso un identificatore come parametro")
            params.append(tok.value)
        return params

    def parse_if(self):
        line = self.advance().line  # 'if'
        self.expect("(", msg="atteso '(' dopo 'if'")
        cond = self.parse_expression()
        self.expect(")", msg="atteso ')' dopo la condizione")
        then_body = self.parse_block()
        else_part = None
        if self.match("KW", "else"):
            if self.at("KW", "if"):
                else_part = self.parse_if()
            else:
                else_part = self.parse_block()
        return IfStmt(cond, then_body, else_part, line)

    def parse_while(self):
        line = self.advance().line  # 'while'
        self.expect("(", msg="atteso '(' dopo 'while'")
        cond = self.parse_expression()
        self.expect(")", msg="atteso ')' dopo la condizione")
        self.loop_depth += 1
        body = self.parse_block()
        self.loop_depth -= 1
        return WhileStmt(cond, body, line)

    def parse_expr_or_assign(self):
        line = self.peek().line
        expr = self.parse_expression()
        if self.at("="):
            self.advance()
            if not isinstance(expr, (Name, Index)):
                self.error("target di assegnamento non valido", line)
            value = self.parse_expression()
            self.expect(";", msg="atteso ';' dopo l'assegnamento")
            return AssignStmt(expr, value, line)
        self.expect(";", msg="atteso ';'")
        return ExprStmt(expr, line)

    # -- expressions -----------------------------------------------------

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at("KW", "or"):
            tok = self.advance()
            right = self.parse_and()
            left = Logical("or", left, right, tok.line)
        return left

    def parse_and(self):
        left = self.parse_equality()
        while self.at("KW", "and"):
            tok = self.advance()
            right = self.parse_equality()
            left = Logical("and", left, right, tok.line)
        return left

    def parse_equality(self):
        left = self.parse_comparison()
        while self.at("==") or self.at("!="):
            tok = self.advance()
            right = self.parse_comparison()
            left = Binary(tok.type, left, right, tok.line)
        return left

    def parse_comparison(self):
        left = self.parse_additive()
        while self.at("<") or self.at("<=") or self.at(">") or self.at(">="):
            tok = self.advance()
            right = self.parse_additive()
            left = Binary(tok.type, left, right, tok.line)
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.at("+") or self.at("-"):
            tok = self.advance()
            right = self.parse_multiplicative()
            left = Binary(tok.type, left, right, tok.line)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.at("*") or self.at("/") or self.at("%"):
            tok = self.advance()
            right = self.parse_unary()
            left = Binary(tok.type, left, right, tok.line)
        return left

    def parse_unary(self):
        if self.at("-") or self.at("KW", "not"):
            tok = self.advance()
            op = "-" if tok.type == "-" else "not"
            operand = self.parse_unary()
            return Unary(op, operand, tok.line)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            if self.at("("):
                line = self.advance().line
                args = []
                if not self.at(")"):
                    args.append(self.parse_expression())
                    while self.match(","):
                        args.append(self.parse_expression())
                self.expect(")", msg="atteso ')' dopo gli argomenti")
                expr = Call(expr, args, line)
            elif self.at("["):
                line = self.advance().line
                idx = self.parse_expression()
                self.expect("]", msg="atteso ']' dopo l'indice")
                expr = Index(expr, idx, line)
            else:
                break
        return expr

    def parse_primary(self):
        tok = self.peek()

        if tok.type == "INT":
            self.advance()
            return IntLit(tok.value, tok.line)
        if tok.type == "STRING":
            self.advance()
            return StringLit(tok.value, tok.line)
        if tok.type == "KW" and tok.value == "true":
            self.advance()
            return BoolLit(True, tok.line)
        if tok.type == "KW" and tok.value == "false":
            self.advance()
            return BoolLit(False, tok.line)
        if tok.type == "KW" and tok.value == "nil":
            self.advance()
            return NilLit(tok.line)
        if tok.type == "IDENT":
            self.advance()
            return Name(tok.value, tok.line)
        if tok.type == "(":
            self.advance()
            expr = self.parse_expression()
            self.expect(")", msg="atteso ')'")
            return expr
        if tok.type == "[":
            self.advance()
            elements = []
            if not self.at("]"):
                elements.append(self.parse_expression())
                while self.match(","):
                    elements.append(self.parse_expression())
            self.expect("]", msg="atteso ']'")
            return ListLit(elements, tok.line)
        if tok.type == "KW" and tok.value == "fn":
            self.advance()
            self.expect("(", msg="atteso '(' dopo 'fn'")
            params = self.parse_param_list()
            self.expect(")", msg="atteso ')' dopo i parametri")
            saved_loop = self.loop_depth
            self.loop_depth = 0
            self.func_depth += 1
            body = self.parse_block()
            self.func_depth -= 1
            self.loop_depth = saved_loop
            return FnLit(params, body, tok.line)

        got = tok.value if tok.value is not None else tok.type
        self.error(f"token inatteso '{got}'", tok.line)


# ---------------------------------------------------------------------------
# Valori runtime
# ---------------------------------------------------------------------------

class MiniFunction:
    __slots__ = ("params", "body", "closure")

    def __init__(self, params, body, closure):
        self.params = params
        self.body = body
        self.closure = closure


class BuiltinFunction:
    __slots__ = ("name", "func")

    def __init__(self, name, func):
        self.name = name
        self.func = func


def type_name(v):
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
    if isinstance(v, (MiniFunction, BuiltinFunction)):
        return "function"
    return "unknown"


def stringify(v, top):
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
        return "[" + ", ".join(stringify(e, False) for e in v) + "]"
    if isinstance(v, (MiniFunction, BuiltinFunction)):
        return "<function>"
    return str(v)


def ml_equals(a, b):
    ta, tb = type_name(a), type_name(b)
    if ta != tb:
        return False
    if ta == "nil":
        return True
    if ta in ("int", "bool", "string"):
        return a == b
    if ta == "list":
        if len(a) != len(b):
            return False
        return all(ml_equals(x, y) for x, y in zip(a, b))
    if ta == "function":
        return a is b
    return False


def trunc_div(a, b):
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def trunc_mod(a, b):
    r = abs(a) % abs(b)
    if a < 0:
        r = -r
    return r


INT_RE = re.compile(r"-?[0-9]+")


# ---------------------------------------------------------------------------
# Control-flow signals
# ---------------------------------------------------------------------------

class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def has_local(self, name):
        return name in self.vars

    def get(self, name):
        e = self
        while e is not None:
            if name in e.vars:
                return e.vars[name]
            e = e.parent
        raise KeyError(name)

    def set(self, name, value):
        e = self
        while e is not None:
            if name in e.vars:
                e.vars[name] = value
                return
            e = e.parent
        raise KeyError(name)


# ---------------------------------------------------------------------------
# Interprete
# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self):
        self.output = []
        self.globals = Env()
        self._install_builtins()

    # -- builtins -------------------------------------------------------

    def _install_builtins(self):
        def _print(args, line):
            self.output.append(" ".join(stringify(a, True) for a in args) + "\n")
            return None

        def _len(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("len() richiede esattamente 1 argomento", line)
            x = args[0]
            if type(x) is str or type(x) is list:
                return len(x)
            raise MiniRuntimeError("len() richiede una string o una list", line)

        def _push(args, line):
            if len(args) != 2:
                raise MiniRuntimeError("push() richiede esattamente 2 argomenti", line)
            xs, v = args
            if type(xs) is not list:
                raise MiniRuntimeError("push() richiede una list", line)
            xs.append(v)
            return None

        def _pop(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("pop() richiede esattamente 1 argomento", line)
            xs = args[0]
            if type(xs) is not list:
                raise MiniRuntimeError("pop() richiede una list", line)
            if len(xs) == 0:
                raise MiniRuntimeError("pop() su una lista vuota", line)
            return xs.pop()

        def _str(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("str() richiede esattamente 1 argomento", line)
            return stringify(args[0], True)

        def _int(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("int() richiede esattamente 1 argomento", line)
            x = args[0]
            if type(x) is int:
                return x
            if type(x) is str:
                if INT_RE.fullmatch(x):
                    return int(x)
                raise MiniRuntimeError(f"impossibile convertire '{x}' in int", line)
            raise MiniRuntimeError("int() richiede una string o un int", line)

        def _type(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("type() richiede esattamente 1 argomento", line)
            return type_name(args[0])

        def _range(args, line):
            if len(args) != 1:
                raise MiniRuntimeError("range() richiede esattamente 1 argomento", line)
            m = args[0]
            if type(m) is not int:
                raise MiniRuntimeError("range() richiede un int", line)
            if m < 0:
                return []
            return list(range(m))

        builtins = {
            "print": _print, "len": _len, "push": _push, "pop": _pop,
            "str": _str, "int": _int, "type": _type, "range": _range,
        }
        for name, fn in builtins.items():
            self.globals.vars[name] = BuiltinFunction(name, fn)

    # -- esecuzione -------------------------------------------------------

    def run_program(self, stmts):
        for s in stmts:
            self.exec_stmt(s, self.globals)

    def exec_block(self, stmts, env):
        for s in stmts:
            self.exec_stmt(s, env)

    def exec_stmt(self, stmt, env):
        t = type(stmt)

        if t is LetStmt:
            value = self.eval_expr(stmt.expr, env)
            if env.has_local(stmt.name):
                raise MiniRuntimeError(
                    f"variabile '{stmt.name}' gia' dichiarata in questo scope", stmt.line)
            env.vars[stmt.name] = value
            return

        if t is AssignStmt:
            value = self.eval_expr(stmt.value, env)
            target = stmt.target
            if isinstance(target, Name):
                try:
                    env.set(target.name, value)
                except KeyError:
                    raise MiniRuntimeError(
                        f"variabile '{target.name}' non dichiarata", target.line)
            else:  # Index
                obj = self.eval_expr(target.obj, env)
                idxv = self.eval_expr(target.index, env)
                if type(obj) is not list:
                    raise MiniRuntimeError(
                        "non e' possibile assegnare a un indice di un valore non list",
                        target.line)
                if type(idxv) is not int:
                    raise MiniRuntimeError("l'indice deve essere un int", target.line)
                i = idxv
                if i < 0:
                    i += len(obj)
                if i < 0 or i >= len(obj):
                    raise MiniRuntimeError("indice fuori range", target.line)
                obj[i] = value
            return

        if t is ExprStmt:
            self.eval_expr(stmt.expr, env)
            return

        if t is BlockStmt:
            new_env = Env(env)
            self.exec_block(stmt.stmts, new_env)
            return

        if t is IfStmt:
            cond_val = self.eval_expr(stmt.cond, env)
            if type(cond_val) is not bool:
                raise MiniRuntimeError("la condizione deve essere bool", stmt.cond.line)
            if cond_val:
                new_env = Env(env)
                self.exec_block(stmt.then_body, new_env)
            else:
                if stmt.else_part is None:
                    pass
                elif isinstance(stmt.else_part, IfStmt):
                    self.exec_stmt(stmt.else_part, env)
                else:
                    new_env = Env(env)
                    self.exec_block(stmt.else_part, new_env)
            return

        if t is WhileStmt:
            while True:
                cond_val = self.eval_expr(stmt.cond, env)
                if type(cond_val) is not bool:
                    raise MiniRuntimeError("la condizione deve essere bool", stmt.cond.line)
                if not cond_val:
                    break
                new_env = Env(env)
                try:
                    self.exec_block(stmt.body, new_env)
                except BreakSignal:
                    break
                except ContinueSignal:
                    continue
            return

        if t is BreakStmt:
            raise BreakSignal()

        if t is ContinueStmt:
            raise ContinueSignal()

        if t is ReturnStmt:
            value = self.eval_expr(stmt.expr, env) if stmt.expr is not None else None
            raise ReturnSignal(value)

        raise AssertionError(f"statement sconosciuto: {t}")

    # -- espressioni -------------------------------------------------------

    def eval_expr(self, expr, env):
        t = type(expr)

        if t is IntLit:
            return expr.value
        if t is StringLit:
            return expr.value
        if t is BoolLit:
            return expr.value
        if t is NilLit:
            return None
        if t is ListLit:
            return [self.eval_expr(e, env) for e in expr.elements]
        if t is FnLit:
            return MiniFunction(expr.params, expr.body, env)
        if t is Name:
            try:
                return env.get(expr.name)
            except KeyError:
                raise MiniRuntimeError(
                    f"variabile '{expr.name}' non dichiarata", expr.line)

        if t is Unary:
            operand = self.eval_expr(expr.operand, env)
            if expr.op == "-":
                if type(operand) is not int:
                    raise MiniRuntimeError(
                        f"operatore unario '-' richiede un int, ricevuto {type_name(operand)}",
                        expr.line)
                return -operand
            else:  # not
                if type(operand) is not bool:
                    raise MiniRuntimeError(
                        f"operatore 'not' richiede un bool, ricevuto {type_name(operand)}",
                        expr.line)
                return not operand

        if t is Logical:
            left = self.eval_expr(expr.left, env)
            if type(left) is not bool:
                raise MiniRuntimeError(
                    f"operando sinistro di '{expr.op}' deve essere bool, ricevuto {type_name(left)}",
                    expr.left.line)
            if expr.op == "or":
                if left:
                    return True
                right = self.eval_expr(expr.right, env)
                if type(right) is not bool:
                    raise MiniRuntimeError(
                        f"operando destro di 'or' deve essere bool, ricevuto {type_name(right)}",
                        expr.right.line)
                return right
            else:  # and
                if not left:
                    return False
                right = self.eval_expr(expr.right, env)
                if type(right) is not bool:
                    raise MiniRuntimeError(
                        f"operando destro di 'and' deve essere bool, ricevuto {type_name(right)}",
                        expr.right.line)
                return right

        if t is Binary:
            return self._eval_binary(expr, env)

        if t is Call:
            callee = self.eval_expr(expr.callee, env)
            args = [self.eval_expr(a, env) for a in expr.args]
            return self.call_function(callee, args, expr.line)

        if t is Index:
            return self._eval_index(expr, env)

        raise AssertionError(f"espressione sconosciuta: {t}")

    def _eval_binary(self, expr, env):
        op = expr.op
        left = self.eval_expr(expr.left, env)
        right = self.eval_expr(expr.right, env)
        line = expr.line

        if op == "+":
            if type(left) is int and type(right) is int:
                return left + right
            if type(left) is str and type(right) is str:
                return left + right
            if type(left) is list and type(right) is list:
                return left + right
            raise MiniRuntimeError(
                f"operatore '+' non supportato tra {type_name(left)} e {type_name(right)}", line)

        if op in ("-", "*", "/", "%"):
            if type(left) is int and type(right) is int:
                if op == "-":
                    return left - right
                if op == "*":
                    return left * right
                if op == "/":
                    if right == 0:
                        raise MiniRuntimeError("divisione per zero", line)
                    return trunc_div(left, right)
                if op == "%":
                    if right == 0:
                        raise MiniRuntimeError("modulo per zero", line)
                    return trunc_mod(left, right)
            raise MiniRuntimeError(
                f"operatore '{op}' non supportato tra {type_name(left)} e {type_name(right)}", line)

        if op in ("<", "<=", ">", ">="):
            if (type(left) is int and type(right) is int) or \
               (type(left) is str and type(right) is str):
                if op == "<":
                    return left < right
                if op == "<=":
                    return left <= right
                if op == ">":
                    return left > right
                return left >= right
            raise MiniRuntimeError(
                f"operatore '{op}' non supportato tra {type_name(left)} e {type_name(right)}", line)

        if op == "==":
            return ml_equals(left, right)
        if op == "!=":
            return not ml_equals(left, right)

        raise AssertionError(f"operatore binario sconosciuto: {op}")

    def _eval_index(self, expr, env):
        obj = self.eval_expr(expr.obj, env)
        idxv = self.eval_expr(expr.index, env)
        if type(idxv) is not int:
            raise MiniRuntimeError("l'indice deve essere un int", expr.line)
        if type(obj) is list:
            n = len(obj)
            i = idxv + n if idxv < 0 else idxv
            if i < 0 or i >= n:
                raise MiniRuntimeError("indice di list fuori range", expr.line)
            return obj[i]
        if type(obj) is str:
            n = len(obj)
            i = idxv + n if idxv < 0 else idxv
            if i < 0 or i >= n:
                raise MiniRuntimeError("indice di string fuori range", expr.line)
            return obj[i]
        raise MiniRuntimeError(
            f"impossibile indicizzare un valore di tipo {type_name(obj)}", expr.line)

    def call_function(self, func, args, call_line):
        if isinstance(func, BuiltinFunction):
            return func.func(args, call_line)
        if isinstance(func, MiniFunction):
            if len(args) != len(func.params):
                raise MiniRuntimeError(
                    f"attesi {len(func.params)} argomenti, ricevuti {len(args)}", call_line)
            new_env = Env(func.closure)
            for p, a in zip(func.params, args):
                new_env.vars[p] = a
            try:
                self.exec_block(func.body, new_env)
            except ReturnSignal as r:
                return r.value
            return None
        raise MiniRuntimeError(
            f"tentativo di chiamare un valore non funzione ({type_name(func)})", call_line)


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def run(source):
    """Esegue il programma MiniLang `source` e restituisce l'output stampato.

    In caso di errore solleva ParseError / MiniRuntimeError; l'output prodotto
    prima dell'errore e' disponibile in `err.output`.
    """
    interp = Interpreter()
    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(max(old_limit, 10000))
        tokens = tokenize(source)
        parser = Parser(tokens)
        program = parser.parse_program()
        interp.run_program(program)
    except MiniLangError as e:
        e.output = "".join(interp.output)
        raise
    except RecursionError:
        e = MiniRuntimeError("ricorsione troppo profonda", 0)
        e.output = "".join(interp.output)
        raise e
    finally:
        sys.setrecursionlimit(old_limit)
    return "".join(interp.output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        sys.stderr.write("uso: python minilang.py <file>\n")
        sys.exit(2)

    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        sys.exit(2)

    try:
        output = run(source)
    except ParseError as e:
        sys.stdout.write(e.output)
        sys.stderr.write(f"ParseError: line {e.line}: {e}\n")
        sys.exit(1)
    except MiniRuntimeError as e:
        sys.stdout.write(e.output)
        sys.stderr.write(f"RuntimeError: line {e.line}: {e}\n")
        sys.exit(1)

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
