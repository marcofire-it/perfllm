# Task 03 — `minilang`: interprete per un piccolo linguaggio

**Livello: 3 (difficile)** · File da consegnare: `minilang.py`, `NOTES.md`

## Obiettivo

Implementare in `minilang.py` (sola libreria standard) un interprete completo — lexer, parser,
valutatore — per il linguaggio **MiniLang** descritto sotto.

## API pubblica (nomi obbligatori)

```python
class MiniLangError(Exception):
    line: int            # riga (1-based) in cui si è verificato l'errore
    output: str          # output prodotto prima dell'errore
class ParseError(MiniLangError): ...       # errori lessicali e sintattici
class MiniRuntimeError(MiniLangError): ... # errori a runtime

def run(source: str) -> str:
    """Esegue il programma e restituisce tutto ciò che è stato stampato (stdout catturato).
    In caso di errore solleva ParseError / MiniRuntimeError. L'output prodotto prima
    dell'errore è recuperabile dall'attributo `output` dell'eccezione (stringa)."""
```

CLI: `python minilang.py <file>` esegue il file stampando l'output su stdout. In caso di errore
stampa comunque su stdout l'output prodotto fino a quel momento, poi su stderr
`ParseError: line N: <messaggio>` oppure `RuntimeError: line N: <messaggio>`
ed esce con codice `1`. Se il file non esiste esce con codice `2`.

## Il linguaggio

### Lessico
- Commenti: da `//` a fine riga.
- Interi: sequenze di cifre decimali, **precisione arbitraria** (il prodotto di numeri grandi non deve andare in overflow).
- Stringhe: tra doppi apici, su una sola riga, con escape `\n`, `\t`, `\\`, `\"`.
- Identificatori: `[A-Za-z_][A-Za-z0-9_]*`. Parole riservate: `let fn return if else while break continue and or not true false nil`.
- Spazi, tab e newline sono separatori. Ogni statement termina con `;` salvo i blocchi `{ }`.

### Tipi e valori
`int`, `bool` (`true`/`false`), `string`, `list`, `function`, `nil`.
Non esistono conversioni implicite: `1 + "a"` è errore, `1 == "1"` vale `false` (non è errore), `if (1)` è errore (la condizione deve essere `bool`).

### Statements
```
let x = expr;                 // dichiarazione (obbligatorio l'inizializzatore)
x = expr;                     // assegnamento a variabile già dichiarata
xs[i] = expr;                 // assegnamento a elemento di lista
expr;                         // expression statement (es. chiamata)
if (cond) { ... } else if (cond) { ... } else { ... }
while (cond) { ... }
break; continue;              // solo dentro un while (altrimenti ParseError)
return expr; return;          // solo dentro una funzione (altrimenti ParseError); `return;` vale nil
fn name(a, b) { ... }         // dichiarazione di funzione (equivale a let name = fn-literal)
{ ... }                       // blocco annidato
```
Le parentesi tonde attorno alla condizione e le graffe attorno ai corpi sono **obbligatorie**.

### Espressioni
Precedenza (dalla più bassa alla più alta), tutti gli operatori binari sono associativi a sinistra:

| livello | operatori |
|---|---|
| 1 | `or` |
| 2 | `and` |
| 3 | `== !=` |
| 4 | `< <= > >=` |
| 5 | `+ -` |
| 6 | `* / %` |
| 7 | unari `-` `not` |
| 8 | chiamata `f(a, b)`, indicizzazione `xs[i]` (postfissi, concatenabili: `f(1)(2)`, `xs[0][1]`) |
| 9 | letterali, identificatori, `( expr )`, `[a, b, c]` (lista), `fn (a, b) { ... }` (funzione anonima) |

Semantica:
- `+ - * / %`: solo tra `int`. `/` è divisione intera **troncata verso zero** e `%` ha il segno del
  **dividendo** (come in C: `-7 / 2 == -3`, `-7 % 2 == -1`). Divisione o modulo per zero ⇒ errore runtime.
- `+` è anche concatenazione `string + string` e `list + list` (nuova lista).
- `< <= > >=`: tra due `int` o tra due `string` (ordine lessicografico per code point). Altrimenti errore.
- `== !=`: confronto **strutturale** per liste, per valore per int/string/bool, `nil == nil` è `true`.
  Tipi diversi ⇒ `false` (mai errore). Funzioni: uguali solo se sono lo stesso oggetto.
- `and` / `or`: **short-circuit**, operandi devono essere `bool` (l'operando destro non viene valutato
  se non serve, quindi `false and (1/0 == 0)` vale `false` senza errore).
- `not`: solo su `bool`. `-` unario: solo su `int`.
- Indicizzazione: solo `list[int]` e `string[int]` (restituisce stringa di 1 carattere). Indici negativi
  contano dalla fine (`xs[-1]` è l'ultimo). Fuori range ⇒ errore runtime.
- Le liste sono **mutabili e condivise per riferimento** (`let b = a; push(b, 1);` modifica anche `a`).

### Funzioni e scoping
- Scoping **lessicale** con blocchi: ogni `{ }` apre uno scope. `let` dichiara nello scope corrente;
  ridichiarare con `let` un nome **già presente nello stesso scope** è errore runtime; nello scope interno
  è ammesso (shadowing).
- Assegnare a un nome mai dichiarato è errore runtime. Leggere un nome non dichiarato è errore runtime.
- Le funzioni sono valori di prima classe e **closure**: catturano le variabili per riferimento
  (un contatore con `n = n + 1` dentro una funzione interna deve modificare la `n` esterna).
- Chiamata con numero di argomenti sbagliato ⇒ errore runtime. Chiamare un non-funzione ⇒ errore runtime.
- Una funzione senza `return` restituisce `nil`.
- La ricorsione deve funzionare almeno fino a **profondità 200** (es. `fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); } print(count(200));`).

### Funzioni built-in
| nome | comportamento |
|---|---|
| `print(a, b, ...)` | stampa gli argomenti separati da uno spazio, seguiti da `\n`. Zero argomenti stampa riga vuota. Restituisce `nil`. |
| `len(x)` | lunghezza di `string` o `list` |
| `push(xs, v)` | aggiunge in coda (in place), restituisce `nil` |
| `pop(xs)` | rimuove e restituisce l'ultimo elemento; lista vuota ⇒ errore runtime |
| `str(x)` | rappresentazione testuale (vedi sotto) |
| `int(s)` | converte una `string` di cifre (con `-` opzionale) in `int`; altrimenti errore runtime; su `int` è identità |
| `type(x)` | una tra `"int" "bool" "string" "list" "function" "nil"` |
| `range(n)` | lista `[0, 1, ..., n-1]` (`n` < 0 ⇒ lista vuota) |

I built-in sono nomi ordinari dello scope globale: possono essere shadowati con `let` in uno scope interno.
Chiamarli con tipi o arità sbagliati ⇒ errore runtime.

### Rappresentazione testuale (usata da `print` e `str`)
- int: cifre decimali; bool: `true`/`false`; nil: `nil`; function: `<function>`.
- string: **al top level** (argomento diretto di `print`/`str`) il contenuto grezzo, senza virgolette.
- list: `[e1, e2, ...]` con separatore `, `; **dentro una lista** le stringhe vanno tra doppi apici
  (senza escape dei caratteri interni): `print([1, "a", [true, nil]])` → `[1, "a", [true, nil]]`.

### Errori
- `ParseError` per: carattere non valido, stringa non terminata, `;` mancante, parentesi sbilanciate,
  `break`/`continue` fuori da un `while`, `return` fuori da una funzione, `let` senza inizializzatore.
- `MiniRuntimeError` per tutto il resto (tipi, nomi, indici, arità, divisione per zero, ...).
- `line` deve essere la riga del token (o dell'espressione) che ha causato l'errore. Per un errore a
  runtime dentro una funzione, la riga è quella dell'espressione che fallisce, non della chiamata.
- Se un'eccezione arriva a `run()`, l'output già prodotto deve essere disponibile in `err.output`.

## Esempio

```
// closure e liste
fn make_counter() {
  let n = 0;
  fn inc() { n = n + 1; return n; }
  return inc;
}
let c = make_counter();
c(); c();
print("count:", c());                 // count: 3

let xs = [3, 1, 2];
fn sort(v) {                          // bubble sort in place
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

## Vincoli

- Sola libreria standard. Nessuna generazione di codice Python (`eval`/`exec` vietati).
- Un `while` con 300 000 iterazioni che fa un paio di operazioni aritmetiche deve completare in meno di 10 s.
- Il file deve essere importabile senza effetti collaterali (`from minilang import run`).
