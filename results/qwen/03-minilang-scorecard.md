# Scorecard — modello: `qwen` · task: `03-minilang` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `84/86` → core `21/22`, edge `61/62`, perf `2/2`
- Test falliti principali e causa (max 5, una riga ciascuno):
  - `test_program[builtins]`: `let r = push([], 1);` assegna `nil` a `r`; alla lettura successiva `_resolve` (righe 648-657) usa `e.vars.get(name)` e tratta `None` come "non dichiarata" → "use of undeclared variable 'r'". Ogni variabile che vale `nil` è invisibile: bug semantico generale, non un caso limite.
  - `test_runtime_errors[builtin_arity]`: `len();` → i built-in leggono `args[0]` senza controllare l'arità (righe 574-630) → `IndexError` Python grezza invece di `MiniRuntimeError`.
- **A = 54/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`run`, eccezioni con `.line`/`.output`, CLI con exit 0/1/2)
- Dipendenze esterne / costrutti vietati: nessuna (`sys`); niente `eval`/`exec`; import senza effetti collaterali (`setrecursionlimit` solo in `run()`, ma **non ripristinato**: resta a 20000 nel processo chiamante)
- Formato consegna (file integrali, NOTES.md): ok (minilang.py, NOTES.md, test_minilang.py, example.ml)
- Deviazioni non documentate: la spec dice "chiamare i built-in con tipi o arità sbagliati ⇒ errore runtime" e NOTES.md lo dichiara implementato, ma il codice non lo fa (-2: assunzione dichiarata falsa). La riga registrata per una chiamata è quella del token **dopo** la `)` (riga 394: `self.peek()[2]`), idem per l'operatore unario (riga 376): su espressioni multi-riga la riga d'errore è sbagliata (-1). Il lexer accetta solo lettere ASCII, coerente con la spec.
- **B = 12/15**

## C. Qualità del codice (15)
- Struttura: `_Lexer` / `_Parser` / `_Interpreter` separati, ma AST a tuple posizionali (`('binop', op, left, right, line)`) documentate solo in un commento: ogni accesso è `n[1]`, `n[2]`, `s[-1]`, fragile e poco leggibile. In `binop` lo spacchettamento `_, op, le, re, line = n` (riga 815) oscura il nome del modulo `re`.
- Gestione errori / thread / risorse: i built-in non validano l'arità (`args[0]` diretto); `_resolve` confonde `nil` con "assente" (riga 652: `if v is not None`) mentre `_lookup` per l'assegnamento usa correttamente `name in e.vars` (riga 662): due percorsi incoerenti per la stessa operazione. `RecursionError` non convertita. `setrecursionlimit` non ripristinato.
- Punti di forza: divisione/modulo C-style corretti e senza float; `_deep_eq` accurata su bool/int; CLI pulita con `OSError` e exit 2; buona docstring iniziale con `__all__`.
- Punti deboli: il bug su `nil` è di quelli che un test minimo (`let x = nil; print(x);`) avrebbe rivelato; l'assegnamento indicizzato è un caso speciale del parser di statement (righe 286-296) invece di riusare le espressioni postfisse.
- **C = 8/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| ricorsione profondità 1000 | ok o errore pulito | `1000` | ok |
| ricorsione profondità 3000 | ok o MiniRuntimeError | `RecursionError` Python grezza | ko |
| 501 addendi `1 + 1 + ...` su una riga | `501` | `501` | ok |
| stringa con escape `\q` | ParseError | ParseError riga 1 | ok |
| `let range = 7;` al top level | errore o shadow | MiniRuntimeError "redeclaration" (documentato) | ok |
| lista che contiene se stessa + `print(a)` | errore pulito o protezione | `RecursionError` grezza | ko |
| `print(1 == 1 == true)` | `true` | `true` | ok |
| sorgente con `\r\n` e tab, errore a riga 5 | riga 5 | riga 5 | ok |
| file con BOM UTF-8 | ParseError o accettato | ParseError riga 1 | ok |
| programma vuoto / soli commenti | `""` | `""` | ok |
| `fn f(a) { let a = 1; return a; } print(f(2));` | 1 o errore | `1` | ok |
| cifra Unicode `²` come letterale | ParseError | ParseError riga 1 (lexer ASCII-only) | ok |
| variabile con valore `nil` riletta e riassegnata | `nil` poi `1` | MiniRuntimeError "undeclared variable 'r'" | ko (bug) |
| `len()` senza argomenti | MiniRuntimeError | `IndexError` Python grezza | ko |
| CLI con directory come argomento | exit 2 pulito | exit 2, messaggio su stderr | ok |
- **D = 3/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, qualità: buono nella forma (architettura, scelte, assunzioni, limiti), ma contiene un'affermazione falsa sull'arità dei built-in.
- Assunzioni dichiarate coerenti con il codice: no (arità built-in)
- Test propri: superficiali/medi (22 test unittest, passano in 0.7 s; molte asserzioni sugli errori runtime ma nessun test su una variabile che vale `nil`, il bug principale)
- **E = 4/5**

## Totale: **81 / 100**

## Commento (5-10 righe)
Consegna quasi completa che passa il 98% dei test nascosti, ma i due fallimenti non sono casi limite: una
variabile inizializzata a `nil` (o al risultato di `push`/`print`) diventa "non dichiarata" perché la
risoluzione dei nomi usa `dict.get` e confonde il valore `None` con l'assenza. È il classico errore Python
che il modello stesso ha evitato nell'altro percorso (assegnamento). I built-in non controllano l'arità e
lasciano trapelare `IndexError`, in contrasto con quanto scritto in NOTES.md. Gestisce correttamente le altre
trappole della spec (divisione troncata, short-circuit, closure, riga dentro la funzione, output parziale).
L'AST a tuple posizionali rende il codice il meno manutenibile dei tre. Non usabile in produzione senza la
correzione di `_resolve` e dei controlli di arità.
