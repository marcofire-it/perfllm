# Task 03 — `minilang`: interpreter for a small language

**Level: 3 (hard)** · Files to deliver: `minilang.py`, `NOTES.md`

## Goal

Implement in `minilang.py` (standard library only) a complete interpreter — lexer, parser,
evaluator — for the **MiniLang** language described below.

## Public API (mandatory names)

```python
class MiniLangError(Exception):
    line: int            # line (1-based) where the error occurred
    output: str          # output produced before the error
class ParseError(MiniLangError): ...       # lexical and syntax errors
class MiniRuntimeError(MiniLangError): ... # runtime errors

def run(source: str) -> str:
    """Runs the program and returns everything that was printed (captured stdout).
    On error raises ParseError / MiniRuntimeError. The output produced before
    the error is available in the exception's `output` attribute (string)."""
```

CLI: `python minilang.py <file>` runs the file printing the output to stdout. On error it
still prints to stdout the output produced so far, then to stderr
`ParseError: line N: <message>` or `RuntimeError: line N: <message>`
and exits with code `1`. If the file does not exist it exits with code `2`.

## The language

### Lexical structure
- Comments: from `//` to end of line.
- Integers: sequences of decimal digits, **arbitrary precision** (the product of large numbers must not overflow).
- Strings: between double quotes, on a single line, with escapes `\n`, `\t`, `\\`, `\"`.
- Identifiers: `[A-Za-z_][A-Za-z0-9_]*`. Reserved words: `let fn return if else while break continue and or not true false nil`.
- Spaces, tabs and newlines are separators. Every statement ends with `;` except `{ }` blocks.

### Types and values
`int`, `bool` (`true`/`false`), `string`, `list`, `function`, `nil`.
There are no implicit conversions: `1 + "a"` is an error, `1 == "1"` is `false` (not an error), `if (1)` is an error (the condition must be a `bool`).

### Statements
```
let x = expr;                 // declaration (initializer mandatory)
x = expr;                     // assignment to an already declared variable
xs[i] = expr;                 // assignment to a list element
expr;                         // expression statement (e.g. a call)
if (cond) { ... } else if (cond) { ... } else { ... }
while (cond) { ... }
break; continue;              // only inside a while (otherwise ParseError)
return expr; return;          // only inside a function (otherwise ParseError); `return;` yields nil
fn name(a, b) { ... }         // function declaration (equivalent to let name = fn-literal)
{ ... }                       // nested block
```
The parentheses around the condition and the braces around the bodies are **mandatory**.

### Expressions
Precedence (from lowest to highest), all binary operators are left-associative:

| level | operators |
|---|---|
| 1 | `or` |
| 2 | `and` |
| 3 | `== !=` |
| 4 | `< <= > >=` |
| 5 | `+ -` |
| 6 | `* / %` |
| 7 | unary `-` `not` |
| 8 | call `f(a, b)`, indexing `xs[i]` (postfix, chainable: `f(1)(2)`, `xs[0][1]`) |
| 9 | literals, identifiers, `( expr )`, `[a, b, c]` (list), `fn (a, b) { ... }` (anonymous function) |

Semantics:
- `+ - * / %`: only between `int`s. `/` is integer division **truncated toward zero** and `%` takes the sign of the
  **dividend** (as in C: `-7 / 2 == -3`, `-7 % 2 == -1`). Division or modulo by zero ⇒ runtime error.
- `+` is also concatenation `string + string` and `list + list` (new list).
- `< <= > >=`: between two `int`s or between two `string`s (lexicographic order by code point). Otherwise error.
- `== !=`: **structural** comparison for lists, by value for int/string/bool, `nil == nil` is `true`.
  Different types ⇒ `false` (never an error). Functions: equal only if they are the same object.
- `and` / `or`: **short-circuit**, operands must be `bool` (the right operand is not evaluated
  if not needed, so `false and (1/0 == 0)` is `false` without error).
- `not`: only on `bool`. Unary `-`: only on `int`.
- Indexing: only `list[int]` and `string[int]` (returns a 1-character string). Negative indices
  count from the end (`xs[-1]` is the last). Out of range ⇒ runtime error.
- Lists are **mutable and shared by reference** (`let b = a; push(b, 1);` also modifies `a`).

### Functions and scoping
- **Lexical** scoping with blocks: every `{ }` opens a scope. `let` declares in the current scope;
  redeclaring with `let` a name **already present in the same scope** is a runtime error; in an inner scope
  it is allowed (shadowing).
- Assigning to a never-declared name is a runtime error. Reading an undeclared name is a runtime error.
- Functions are first-class values and **closures**: they capture variables by reference
  (a counter with `n = n + 1` inside an inner function must modify the outer `n`).
- A call with the wrong number of arguments ⇒ runtime error. Calling a non-function ⇒ runtime error.
- A function without `return` returns `nil`.
- Recursion must work at least to **depth 200** (e.g. `fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); } print(count(200));`).

### Built-in functions
| name | behaviour |
|---|---|
| `print(a, b, ...)` | prints the arguments separated by one space, followed by `\n`. Zero arguments prints an empty line. Returns `nil`. |
| `len(x)` | length of a `string` or `list` |
| `push(xs, v)` | appends at the end (in place), returns `nil` |
| `pop(xs)` | removes and returns the last element; empty list ⇒ runtime error |
| `str(x)` | textual representation (see below) |
| `int(s)` | converts a `string` of digits (with optional `-`) into an `int`; otherwise runtime error; on an `int` it is the identity |
| `type(x)` | one of `"int" "bool" "string" "list" "function" "nil"` |
| `range(n)` | list `[0, 1, ..., n-1]` (`n` < 0 ⇒ empty list) |

Built-ins are ordinary names in the global scope: they can be shadowed with `let` in an inner scope.
Calling them with wrong types or arity ⇒ runtime error.

### Textual representation (used by `print` and `str`)
- int: decimal digits; bool: `true`/`false`; nil: `nil`; function: `<function>`.
- string: **at top level** (direct argument of `print`/`str`) the raw content, without quotes.
- list: `[e1, e2, ...]` with separator `, `; **inside a list** strings go between double quotes
  (without escaping the inner characters): `print([1, "a", [true, nil]])` → `[1, "a", [true, nil]]`.

### Errors
- `ParseError` for: invalid character, unterminated string, missing `;`, unbalanced parentheses,
  `break`/`continue` outside a `while`, `return` outside a function, `let` without initializer.
- `MiniRuntimeError` for everything else (types, names, indices, arity, division by zero, ...).
- `line` must be the line of the token (or expression) that caused the error. For a runtime error
  inside a function, the line is that of the failing expression, not of the call.
- If an exception reaches `run()`, the output already produced must be available in `err.output`.

## Example

```
// closures and lists
fn make_counter() {
  let n = 0;
  fn inc() { n = n + 1; return n; }
  return inc;
}
let c = make_counter();
c(); c();
print("count:", c());                 // count: 3

let xs = [3, 1, 2];
fn sort(v) {                          // in-place bubble sort
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
print(xs, len(xs), xs[-1]);           // [1, 2, 3] 3 3
print(-7 / 2, -7 % 2, 7 / -2);        // -3 -1 -3
print(str(12) + "!", type(nil));      // 12! nil
```

## Constraints

- Standard library only. No Python code generation (`eval`/`exec` forbidden).
- A `while` with 300 000 iterations doing a couple of arithmetic operations must complete in under 10 s.
- The file must be importable without side effects (`from minilang import run`).
