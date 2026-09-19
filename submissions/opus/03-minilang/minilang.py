#!/usr/bin/env python3
"""MiniLang interpreter – lexer, parser, evaluator.  Solo libreria standard."""

import sys

# ═══════════════════════════════════════════════════════════════════
#  Exceptions
# ═══════════════════════════════════════════════════════════════════

class MiniLangError(Exception):
    """Base error for MiniLang."""
    def __init__(self, message, line=0, output=""):
        super().__init__(message)
        self.line = line
        self.output = output


class ParseError(MiniLangError):
    """Lexical / syntactic errors."""
    pass


class MiniRuntimeError(MiniLangError):
    """Runtime errors."""
    pass


# ═══════════════════════════════════════════════════════════════════
#  Lexer
# ═══════════════════════════════════════════════════════════════════

_KEYWORDS = frozenset([
    "let", "fn", "return", "if", "else", "while",
    "break", "continue", "and", "or", "not",
    "true", "false", "nil",
])

_TWO_CHAR_OPS = frozenset(["==", "!=", "<=", ">="])
_SINGLE_CHARS = frozenset("+-*/%=<>(){}[];,")


class Token:
    """A lexical token.  *tp* is the token type string."""
    __slots__ = ("tp", "val", "ln")

    def __init__(self, tp: str, val, ln: int):
        self.tp = tp
        self.val = val
        self.ln = ln


def _lex(source: str) -> list:
    """Tokenize *source* and return a list of Token (last one is EOF)."""
    tokens: list[Token] = []
    i = 0
    ln = 1
    n = len(source)

    while i < n:
        c = source[i]

        # whitespace
        if c in " \t\r":
            i += 1
            continue
        if c == "\n":
            ln += 1
            i += 1
            continue

        # comments
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue

        # integer literal
        if c.isdigit():
            j = i
            while j < n and source[j].isdigit():
                j += 1
            tokens.append(Token("INT", int(source[i:j]), ln))
            i = j
            continue

        # string literal
        if c == '"':
            start_ln = ln
            i += 1
            chars: list[str] = []
            while i < n:
                c2 = source[i]
                if c2 == "\n":
                    raise ParseError("Unterminated string literal", start_ln)
                if c2 == '"':
                    tokens.append(Token("STR", "".join(chars), start_ln))
                    i += 1
                    break
                if c2 == "\\":
                    i += 1
                    if i >= n:
                        raise ParseError("Unterminated string literal", start_ln)
                    esc = source[i]
                    if esc == "n":
                        chars.append("\n")
                    elif esc == "t":
                        chars.append("\t")
                    elif esc == "\\":
                        chars.append("\\")
                    elif esc == '"':
                        chars.append('"')
                    else:
                        raise ParseError(f"Invalid escape sequence: \\{esc}", start_ln)
                else:
                    chars.append(c2)
                i += 1
            else:
                raise ParseError("Unterminated string literal", start_ln)
            continue

        # identifier / keyword
        if c.isalpha() or c == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            tp = word if word in _KEYWORDS else "ID"
            tokens.append(Token(tp, word, ln))
            i = j
            continue

        # two-character operators
        if i + 1 < n and source[i : i + 2] in _TWO_CHAR_OPS:
            two = source[i : i + 2]
            tokens.append(Token(two, two, ln))
            i += 2
            continue

        # single-character tokens
        if c in _SINGLE_CHARS:
            tokens.append(Token(c, c, ln))
            i += 1
            continue

        raise ParseError(f"Unexpected character: {c!r}", ln)

    tokens.append(Token("EOF", None, ln))
    return tokens


# ═══════════════════════════════════════════════════════════════════
#  AST nodes
# ═══════════════════════════════════════════════════════════════════

# --- Statements ---

class LetStmt:
    __slots__ = ("name", "expr", "ln")
    def __init__(self, name, expr, ln):
        self.name = name; self.expr = expr; self.ln = ln

class AssignStmt:
    __slots__ = ("name", "expr", "ln")
    def __init__(self, name, expr, ln):
        self.name = name; self.expr = expr; self.ln = ln

class IdxAssignStmt:
    __slots__ = ("obj", "idx", "expr", "ln")
    def __init__(self, obj, idx, expr, ln):
        self.obj = obj; self.idx = idx; self.expr = expr; self.ln = ln

class ExprStmt:
    __slots__ = ("expr",)
    def __init__(self, expr):
        self.expr = expr

class IfStmt:
    __slots__ = ("cond", "then_body", "else_body", "ln")
    def __init__(self, cond, then_body, else_body, ln):
        self.cond = cond; self.then_body = then_body
        self.else_body = else_body; self.ln = ln

class WhileStmt:
    __slots__ = ("cond", "body", "ln")
    def __init__(self, cond, body, ln):
        self.cond = cond; self.body = body; self.ln = ln

class BreakStmt:
    __slots__ = ("ln",)
    def __init__(self, ln):
        self.ln = ln

class ContinueStmt:
    __slots__ = ("ln",)
    def __init__(self, ln):
        self.ln = ln

class ReturnStmt:
    __slots__ = ("expr", "ln")
    def __init__(self, expr, ln):
        self.expr = expr; self.ln = ln

class BlockStmt:
    __slots__ = ("stmts", "ln")
    def __init__(self, stmts, ln):
        self.stmts = stmts; self.ln = ln

class FnDeclStmt:
    __slots__ = ("name", "params", "body", "ln")
    def __init__(self, name, params, body, ln):
        self.name = name; self.params = params
        self.body = body; self.ln = ln

# --- Expressions ---

class IntExpr:
    __slots__ = ("val", "ln")
    def __init__(self, val, ln):
        self.val = val; self.ln = ln

class StrExpr:
    __slots__ = ("val", "ln")
    def __init__(self, val, ln):
        self.val = val; self.ln = ln

class BoolExpr:
    __slots__ = ("val", "ln")
    def __init__(self, val, ln):
        self.val = val; self.ln = ln

class NilExpr:
    __slots__ = ("ln",)
    def __init__(self, ln):
        self.ln = ln

class IdExpr:
    __slots__ = ("name", "ln")
    def __init__(self, name, ln):
        self.name = name; self.ln = ln

class UnaryExpr:
    __slots__ = ("op", "operand", "ln")
    def __init__(self, op, operand, ln):
        self.op = op; self.operand = operand; self.ln = ln

class BinExpr:
    __slots__ = ("op", "left", "right", "ln")
    def __init__(self, op, left, right, ln):
        self.op = op; self.left = left; self.right = right; self.ln = ln

class CallExpr:
    __slots__ = ("callee", "args", "ln")
    def __init__(self, callee, args, ln):
        self.callee = callee; self.args = args; self.ln = ln

class IdxExpr:
    __slots__ = ("obj", "idx", "ln")
    def __init__(self, obj, idx, ln):
        self.obj = obj; self.idx = idx; self.ln = ln

class ListExpr:
    __slots__ = ("elems", "ln")
    def __init__(self, elems, ln):
        self.elems = elems; self.ln = ln

class FnExpr:
    __slots__ = ("params", "body", "ln")
    def __init__(self, params, body, ln):
        self.params = params; self.body = body; self.ln = ln


# ═══════════════════════════════════════════════════════════════════
#  Parser  (recursive descent)
# ═══════════════════════════════════════════════════════════════════

class Parser:
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
        self._loop_depth = 0
        self._func_depth = 0

    # -- helpers ------------------------------------------------
    def _cur(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _expect(self, tp: str, msg: str = "") -> Token:
        t = self._cur()
        if t.tp != tp:
            raise ParseError(msg or f"Expected '{tp}', got '{t.tp}'", t.ln)
        return self._advance()

    def _match(self, tp: str):
        if self._cur().tp == tp:
            return self._advance()
        return None

    def _at(self, tp: str) -> bool:
        return self._cur().tp == tp

    # -- program ------------------------------------------------
    def parse_program(self) -> list:
        stmts: list = []
        while not self._at("EOF"):
            stmts.append(self._stmt())
        return stmts

    # -- statements ---------------------------------------------
    def _stmt(self):
        t = self._cur()

        if t.tp == "let":
            return self._let_stmt()

        if t.tp == "fn":
            # fn NAME( → declaration; anything else → expression-stmt
            if (self.pos + 2 < len(self.tokens)
                    and self.tokens[self.pos + 1].tp == "ID"
                    and self.tokens[self.pos + 2].tp == "("):
                return self._fn_decl()
            return self._expr_or_assign()

        if t.tp == "if":
            return self._if_stmt()

        if t.tp == "while":
            return self._while_stmt()

        if t.tp == "break":
            if self._loop_depth == 0:
                raise ParseError("'break' outside of loop", t.ln)
            self._advance()
            self._expect(";", "Expected ';' after 'break'")
            return BreakStmt(t.ln)

        if t.tp == "continue":
            if self._loop_depth == 0:
                raise ParseError("'continue' outside of loop", t.ln)
            self._advance()
            self._expect(";", "Expected ';' after 'continue'")
            return ContinueStmt(t.ln)

        if t.tp == "return":
            if self._func_depth == 0:
                raise ParseError("'return' outside of function", t.ln)
            self._advance()
            expr = None
            if not self._at(";"):
                expr = self._expr()
            self._expect(";", "Expected ';' after return")
            return ReturnStmt(expr, t.ln)

        if t.tp == "{":
            return self._block()

        return self._expr_or_assign()

    def _let_stmt(self):
        t = self._advance()                          # 'let'
        name = self._expect("ID", "Expected identifier after 'let'")
        self._expect("=", "Expected '=' in let declaration")
        expr = self._expr()
        self._expect(";", "Expected ';' after let declaration")
        return LetStmt(name.val, expr, t.ln)

    def _fn_decl(self):
        t = self._advance()                          # 'fn'
        name = self._expect("ID", "Expected function name")
        self._expect("(", "Expected '(' after function name")
        params = self._param_list()
        self._expect(")", "Expected ')' after parameters")
        saved = self._loop_depth
        self._loop_depth = 0
        self._func_depth += 1
        body = self._block()
        self._func_depth -= 1
        self._loop_depth = saved
        return FnDeclStmt(name.val, params, body, t.ln)

    def _param_list(self) -> list:
        params: list[str] = []
        if not self._at(")"):
            params.append(self._expect("ID", "Expected parameter name").val)
            while self._match(","):
                params.append(self._expect("ID", "Expected parameter name").val)
        return params

    def _if_stmt(self):
        t = self._advance()                          # 'if'
        self._expect("(", "Expected '(' after 'if'")
        cond = self._expr()
        self._expect(")", "Expected ')' after condition")
        then_body = self._block()
        else_body = None
        if self._match("else"):
            if self._at("if"):
                else_body = self._if_stmt()
            else:
                else_body = self._block()
        return IfStmt(cond, then_body, else_body, t.ln)

    def _while_stmt(self):
        t = self._advance()                          # 'while'
        self._expect("(", "Expected '(' after 'while'")
        cond = self._expr()
        self._expect(")", "Expected ')' after condition")
        self._loop_depth += 1
        body = self._block()
        self._loop_depth -= 1
        return WhileStmt(cond, body, t.ln)

    def _block(self):
        t = self._expect("{", "Expected '{'")
        stmts: list = []
        while not self._at("}"):
            if self._at("EOF"):
                raise ParseError("Unexpected end of input, expected '}'", t.ln)
            stmts.append(self._stmt())
        self._expect("}", "Expected '}'")
        return BlockStmt(stmts, t.ln)

    def _expr_or_assign(self):
        expr = self._expr()
        if self._at("="):
            self._advance()
            if isinstance(expr, IdExpr):
                rhs = self._expr()
                self._expect(";", "Expected ';' after assignment")
                return AssignStmt(expr.name, rhs, expr.ln)
            if isinstance(expr, IdxExpr):
                rhs = self._expr()
                self._expect(";", "Expected ';' after index assignment")
                return IdxAssignStmt(expr.obj, expr.idx, rhs, expr.ln)
            raise ParseError("Invalid assignment target", expr.ln)
        self._expect(";", "Expected ';' after expression statement")
        return ExprStmt(expr)

    # -- expressions (precedence climbing) ----------------------

    def _expr(self):
        return self._or()

    def _or(self):
        node = self._and()
        while self._at("or"):
            t = self._advance()
            node = BinExpr("or", node, self._and(), t.ln)
        return node

    def _and(self):
        node = self._equality()
        while self._at("and"):
            t = self._advance()
            node = BinExpr("and", node, self._equality(), t.ln)
        return node

    def _equality(self):
        node = self._comparison()
        while self._cur().tp in ("==", "!="):
            t = self._advance()
            node = BinExpr(t.val, node, self._comparison(), t.ln)
        return node

    def _comparison(self):
        node = self._addition()
        while self._cur().tp in ("<", "<=", ">", ">="):
            t = self._advance()
            node = BinExpr(t.val, node, self._addition(), t.ln)
        return node

    def _addition(self):
        node = self._multiplication()
        while self._cur().tp in ("+", "-"):
            t = self._advance()
            node = BinExpr(t.val, node, self._multiplication(), t.ln)
        return node

    def _multiplication(self):
        node = self._unary()
        while self._cur().tp in ("*", "/", "%"):
            t = self._advance()
            node = BinExpr(t.val, node, self._unary(), t.ln)
        return node

    def _unary(self):
        if self._at("-"):
            t = self._advance()
            return UnaryExpr("-", self._unary(), t.ln)
        if self._at("not"):
            t = self._advance()
            return UnaryExpr("not", self._unary(), t.ln)
        return self._postfix()

    def _postfix(self):
        node = self._primary()
        while True:
            if self._at("("):
                t = self._advance()
                args: list = []
                if not self._at(")"):
                    args.append(self._expr())
                    while self._match(","):
                        args.append(self._expr())
                self._expect(")", "Expected ')' after arguments")
                node = CallExpr(node, args, t.ln)
            elif self._at("["):
                t = self._advance()
                idx = self._expr()
                self._expect("]", "Expected ']' after index")
                node = IdxExpr(node, idx, t.ln)
            else:
                break
        return node

    def _primary(self):
        t = self._cur()

        if t.tp == "INT":
            self._advance()
            return IntExpr(t.val, t.ln)

        if t.tp == "STR":
            self._advance()
            return StrExpr(t.val, t.ln)

        if t.tp == "true":
            self._advance()
            return BoolExpr(True, t.ln)

        if t.tp == "false":
            self._advance()
            return BoolExpr(False, t.ln)

        if t.tp == "nil":
            self._advance()
            return NilExpr(t.ln)

        if t.tp == "ID":
            self._advance()
            return IdExpr(t.val, t.ln)

        if t.tp == "(":
            self._advance()
            expr = self._expr()
            self._expect(")", "Expected ')'")
            return expr

        if t.tp == "[":
            self._advance()
            elems: list = []
            if not self._at("]"):
                elems.append(self._expr())
                while self._match(","):
                    elems.append(self._expr())
            self._expect("]", "Expected ']'")
            return ListExpr(elems, t.ln)

        if t.tp == "fn":
            return self._fn_expr()

        raise ParseError(f"Unexpected token: {t.val!r}", t.ln)

    def _fn_expr(self):
        t = self._advance()                          # 'fn'
        self._expect("(", "Expected '(' after 'fn'")
        params = self._param_list()
        self._expect(")", "Expected ')' after parameters")
        saved = self._loop_depth
        self._loop_depth = 0
        self._func_depth += 1
        body = self._block()
        self._func_depth -= 1
        self._loop_depth = saved
        return FnExpr(params, body, t.ln)


# ═══════════════════════════════════════════════════════════════════
#  Runtime values & environment
# ═══════════════════════════════════════════════════════════════════

_SENTINEL = object()                 # marks "name not found"


class Env:
    """Lexical scope (linked-list chain)."""
    __slots__ = ("parent", "vars")

    def __init__(self, parent=None):
        self.parent = parent
        self.vars: dict = {}

    def get(self, name: str):
        """Return value or _SENTINEL."""
        env = self
        while env is not None:
            v = env.vars.get(name, _SENTINEL)
            if v is not _SENTINEL:
                return v
            env = env.parent
        return _SENTINEL

    def set(self, name: str, value) -> bool:
        """Assign to an existing binding.  Returns False if not found."""
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return True
            env = env.parent
        return False


class Closure:
    """User-defined function (first-class, closure)."""
    __slots__ = ("params", "body", "env")

    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env


class Builtin:
    """Built-in function wrapper."""
    __slots__ = ("name", "fn")

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn


# -- control-flow signals (not user-visible exceptions) --

class _SigBreak(BaseException):
    pass

class _SigContinue(BaseException):
    pass

class _SigReturn(BaseException):
    __slots__ = ("value",)
    def __init__(self, value):
        self.value = value


# ═══════════════════════════════════════════════════════════════════
#  Interpreter
# ═══════════════════════════════════════════════════════════════════

class _Interp:
    def __init__(self):
        self._out: list[str] = []
        self.genv = Env()
        self._install_builtins()

    # -- helpers ------------------------------------------------

    def output(self) -> str:
        return "".join(self._out)

    def _err(self, msg: str, ln: int) -> MiniRuntimeError:
        return MiniRuntimeError(msg, ln, self.output())

    @staticmethod
    def _tname(v) -> str:
        if v is None:
            return "nil"
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, str):
            return "string"
        if isinstance(v, list):
            return "list"
        if isinstance(v, (Closure, Builtin)):
            return "function"
        return "unknown"

    def _fmt(self, v, inside_list: bool = False) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return '"' + v + '"' if inside_list else v
        if v is None:
            return "nil"
        if isinstance(v, list):
            return "[" + ", ".join(self._fmt(e, True) for e in v) + "]"
        if isinstance(v, (Closure, Builtin)):
            return "<function>"
        return str(v)

    # -- builtins -----------------------------------------------

    def _install_builtins(self):
        defs = [
            ("print", self._bi_print),
            ("len",   self._bi_len),
            ("push",  self._bi_push),
            ("pop",   self._bi_pop),
            ("str",   self._bi_str),
            ("int",   self._bi_int),
            ("type",  self._bi_type),
            ("range", self._bi_range),
        ]
        for name, fn in defs:
            self.genv.vars[name] = Builtin(name, fn)

    def _bi_print(self, args, ln):
        self._out.append(" ".join(self._fmt(a) for a in args) + "\n")
        return None

    def _bi_len(self, args, ln):
        if len(args) != 1:
            raise self._err(f"len() takes 1 argument, got {len(args)}", ln)
        v = args[0]
        if isinstance(v, (str, list)):
            return len(v)
        raise self._err(f"len() requires string or list, got {self._tname(v)}", ln)

    def _bi_push(self, args, ln):
        if len(args) != 2:
            raise self._err(f"push() takes 2 arguments, got {len(args)}", ln)
        if not isinstance(args[0], list):
            raise self._err(f"push() requires list, got {self._tname(args[0])}", ln)
        args[0].append(args[1])
        return None

    def _bi_pop(self, args, ln):
        if len(args) != 1:
            raise self._err(f"pop() takes 1 argument, got {len(args)}", ln)
        if not isinstance(args[0], list):
            raise self._err(f"pop() requires list, got {self._tname(args[0])}", ln)
        if not args[0]:
            raise self._err("pop() on empty list", ln)
        return args[0].pop()

    def _bi_str(self, args, ln):
        if len(args) != 1:
            raise self._err(f"str() takes 1 argument, got {len(args)}", ln)
        return self._fmt(args[0])

    def _bi_int(self, args, ln):
        if len(args) != 1:
            raise self._err(f"int() takes 1 argument, got {len(args)}", ln)
        v = args[0]
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v
            digits = s[1:] if s.startswith("-") else s
            if digits and digits.isdigit():
                return int(s)
            raise self._err(f"int() cannot convert {v!r} to int", ln)
        raise self._err(f"int() requires int or string, got {self._tname(v)}", ln)

    def _bi_type(self, args, ln):
        if len(args) != 1:
            raise self._err(f"type() takes 1 argument, got {len(args)}", ln)
        return self._tname(args[0])

    def _bi_range(self, args, ln):
        if len(args) != 1:
            raise self._err(f"range() takes 1 argument, got {len(args)}", ln)
        v = args[0]
        if not isinstance(v, int) or isinstance(v, bool):
            raise self._err(f"range() requires int, got {self._tname(v)}", ln)
        return list(range(max(v, 0)))

    # -- statement execution ------------------------------------

    def run_stmts(self, stmts, env: Env):
        for s in stmts:
            self._exec(s, env)

    def _exec(self, stmt, env: Env):

        if isinstance(stmt, LetStmt):
            val = self._eval(stmt.expr, env)
            if stmt.name in env.vars:
                raise self._err(
                    f"Variable '{stmt.name}' already declared in this scope",
                    stmt.ln)
            env.vars[stmt.name] = val
            return

        if isinstance(stmt, AssignStmt):
            val = self._eval(stmt.expr, env)
            if not env.set(stmt.name, val):
                raise self._err(f"Undefined variable '{stmt.name}'", stmt.ln)
            return

        if isinstance(stmt, IdxAssignStmt):
            obj = self._eval(stmt.obj, env)
            idx = self._eval(stmt.idx, env)
            val = self._eval(stmt.expr, env)
            if not isinstance(obj, list):
                raise self._err(
                    f"Cannot index-assign to {self._tname(obj)}", stmt.ln)
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise self._err(
                    f"Index must be int, got {self._tname(idx)}", stmt.ln)
            n = len(obj)
            if idx < -n or idx >= n:
                raise self._err(
                    f"Index {idx} out of range for list of length {n}", stmt.ln)
            obj[idx] = val
            return

        if isinstance(stmt, ExprStmt):
            self._eval(stmt.expr, env)
            return

        if isinstance(stmt, IfStmt):
            cond = self._eval(stmt.cond, env)
            if not isinstance(cond, bool):
                raise self._err(
                    f"Condition must be bool, got {self._tname(cond)}",
                    stmt.cond.ln)
            if cond:
                self._exec(stmt.then_body, env)
            elif stmt.else_body is not None:
                self._exec(stmt.else_body, env)
            return

        if isinstance(stmt, WhileStmt):
            while True:
                cond = self._eval(stmt.cond, env)
                if not isinstance(cond, bool):
                    raise self._err(
                        f"Condition must be bool, got {self._tname(cond)}",
                        stmt.cond.ln)
                if not cond:
                    break
                try:
                    self._exec(stmt.body, env)
                except _SigBreak:
                    break
                except _SigContinue:
                    continue
            return

        if isinstance(stmt, BreakStmt):
            raise _SigBreak()

        if isinstance(stmt, ContinueStmt):
            raise _SigContinue()

        if isinstance(stmt, ReturnStmt):
            val = self._eval(stmt.expr, env) if stmt.expr is not None else None
            raise _SigReturn(val)

        if isinstance(stmt, BlockStmt):
            inner = Env(env)
            self.run_stmts(stmt.stmts, inner)
            return

        if isinstance(stmt, FnDeclStmt):
            fn = Closure(stmt.params, stmt.body, env)
            if stmt.name in env.vars:
                raise self._err(
                    f"Variable '{stmt.name}' already declared in this scope",
                    stmt.ln)
            env.vars[stmt.name] = fn
            return

    # -- expression evaluation ----------------------------------

    def _eval(self, expr, env: Env):

        if isinstance(expr, IntExpr):
            return expr.val
        if isinstance(expr, StrExpr):
            return expr.val
        if isinstance(expr, BoolExpr):
            return expr.val
        if isinstance(expr, NilExpr):
            return None

        if isinstance(expr, IdExpr):
            v = env.get(expr.name)
            if v is _SENTINEL:
                raise self._err(f"Undefined variable '{expr.name}'", expr.ln)
            return v

        if isinstance(expr, UnaryExpr):
            val = self._eval(expr.operand, env)
            if expr.op == "-":
                if not isinstance(val, int) or isinstance(val, bool):
                    raise self._err(
                        f"Unary '-' requires int, got {self._tname(val)}",
                        expr.ln)
                return -val
            # 'not'
            if not isinstance(val, bool):
                raise self._err(
                    f"'not' requires bool, got {self._tname(val)}", expr.ln)
            return not val

        if isinstance(expr, BinExpr):
            return self._eval_bin(expr, env)

        if isinstance(expr, CallExpr):
            return self._eval_call(expr, env)

        if isinstance(expr, IdxExpr):
            return self._eval_idx(expr, env)

        if isinstance(expr, ListExpr):
            return [self._eval(e, env) for e in expr.elems]

        if isinstance(expr, FnExpr):
            return Closure(expr.params, expr.body, env)

        raise self._err("Unknown expression", getattr(expr, "ln", 0))  # pragma: no cover

    # -- binary operators ---------------------------------------

    def _eval_bin(self, expr: BinExpr, env: Env):
        op = expr.op

        # short-circuit: or / and
        if op == "or":
            left = self._eval(expr.left, env)
            if not isinstance(left, bool):
                raise self._err(
                    f"'or' requires bool operands, got {self._tname(left)}",
                    expr.ln)
            if left:
                return True
            right = self._eval(expr.right, env)
            if not isinstance(right, bool):
                raise self._err(
                    f"'or' requires bool operands, got {self._tname(right)}",
                    expr.ln)
            return right

        if op == "and":
            left = self._eval(expr.left, env)
            if not isinstance(left, bool):
                raise self._err(
                    f"'and' requires bool operands, got {self._tname(left)}",
                    expr.ln)
            if not left:
                return False
            right = self._eval(expr.right, env)
            if not isinstance(right, bool):
                raise self._err(
                    f"'and' requires bool operands, got {self._tname(right)}",
                    expr.ln)
            return right

        left = self._eval(expr.left, env)
        right = self._eval(expr.right, env)

        # equality (never errors on type mismatch)
        if op == "==":
            return self._eq(left, right)
        if op == "!=":
            return not self._eq(left, right)

        lt = self._tname(left)
        rt = self._tname(right)

        # comparison
        if op in ("<", "<=", ">", ">="):
            if lt == "int" and rt == "int":
                if op == "<":  return left < right
                if op == "<=": return left <= right
                if op == ">":  return left > right
                return left >= right
            if lt == "string" and rt == "string":
                if op == "<":  return left < right
                if op == "<=": return left <= right
                if op == ">":  return left > right
                return left >= right
            raise self._err(
                f"Cannot compare {lt} and {rt} with '{op}'", expr.ln)

        # arithmetic / concat
        if op == "+":
            if lt == "int" and rt == "int":
                return left + right
            if lt == "string" and rt == "string":
                return left + right
            if lt == "list" and rt == "list":
                return left + right          # new list
            raise self._err(f"Cannot use '+' on {lt} and {rt}", expr.ln)

        if op == "-":
            if lt == "int" and rt == "int":
                return left - right
            raise self._err(f"Cannot use '-' on {lt} and {rt}", expr.ln)

        if op == "*":
            if lt == "int" and rt == "int":
                return left * right
            raise self._err(f"Cannot use '*' on {lt} and {rt}", expr.ln)

        if op == "/":
            if lt == "int" and rt == "int":
                if right == 0:
                    raise self._err("Division by zero", expr.ln)
                # C-style truncation toward zero
                q = abs(left) // abs(right)
                if (left < 0) != (right < 0):
                    q = -q
                return q
            raise self._err(f"Cannot use '/' on {lt} and {rt}", expr.ln)

        if op == "%":
            if lt == "int" and rt == "int":
                if right == 0:
                    raise self._err("Modulo by zero", expr.ln)
                # C-style: sign of dividend
                r = abs(left) % abs(right)
                if left < 0:
                    r = -r
                return r
            raise self._err(f"Cannot use '%' on {lt} and {rt}", expr.ln)

        raise self._err(f"Unknown operator '{op}'", expr.ln)  # pragma: no cover

    # -- structural equality ------------------------------------

    def _eq(self, a, b) -> bool:
        ta = self._tname(a)
        tb = self._tname(b)
        if ta != tb:
            return False
        if ta == "list":
            if len(a) != len(b):
                return False
            return all(self._eq(x, y) for x, y in zip(a, b))
        if ta == "function":
            return a is b
        return a == b

    # -- function call ------------------------------------------

    def _eval_call(self, expr: CallExpr, env: Env):
        callee = self._eval(expr.callee, env)
        args = [self._eval(a, env) for a in expr.args]

        if isinstance(callee, Builtin):
            return callee.fn(args, expr.ln)

        if isinstance(callee, Closure):
            if len(args) != len(callee.params):
                raise self._err(
                    f"Expected {len(callee.params)} argument(s), got {len(args)}",
                    expr.ln)
            # The call environment holds the parameters; the body block
            # will create its own child scope for local let-declarations.
            call_env = Env(callee.env)
            for p, v in zip(callee.params, args):
                call_env.vars[p] = v
            try:
                self._exec(callee.body, call_env)
            except _SigReturn as sig:
                return sig.value
            return None

        raise self._err(f"Cannot call {self._tname(callee)}", expr.ln)

    # -- indexing -----------------------------------------------

    def _eval_idx(self, expr: IdxExpr, env: Env):
        obj = self._eval(expr.obj, env)
        idx = self._eval(expr.idx, env)

        if isinstance(obj, (list, str)):
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise self._err(
                    f"Index must be int, got {self._tname(idx)}", expr.ln)
            n = len(obj)
            if idx < -n or idx >= n:
                raise self._err(
                    f"Index {idx} out of range for {self._tname(obj)} of length {n}",
                    expr.ln)
            return obj[idx]

        raise self._err(f"Cannot index {self._tname(obj)}", expr.ln)


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════

def run(source: str) -> str:
    """Execute a MiniLang program and return captured output.

    Raises ParseError or MiniRuntimeError on failure; the *output*
    attribute of the exception contains output produced before the error.
    """
    old_limit = sys.getrecursionlimit()
    if old_limit < 10000:
        sys.setrecursionlimit(10000)
    try:
        # Lex & parse
        tokens = _lex(source)
        stmts = Parser(tokens).parse_program()

        # Execute
        interp = _Interp()
        try:
            interp.run_stmts(stmts, interp.genv)
            return interp.output()
        except MiniLangError as exc:
            exc.output = interp.output()
            raise
    except MiniLangError:
        raise                            # output already set
    finally:
        sys.setrecursionlimit(old_limit)


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python minilang.py <file>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        sys.exit(2)

    try:
        result = run(source)
        sys.stdout.write(result)
    except ParseError as exc:
        sys.stdout.write(exc.output)
        print(f"ParseError: line {exc.line}: {exc}", file=sys.stderr)
        sys.exit(1)
    except MiniRuntimeError as exc:
        sys.stdout.write(exc.output)
        print(f"RuntimeError: line {exc.line}: {exc}", file=sys.stderr)
        sys.exit(1)
