# NOTES — minilang.py

## Architettura

L'interprete è composto da tre fasi classiche, tutte nello stesso file:

1. **Lexer** (`_lex`): tokenizzazione single-pass, restituisce una lista di `Token`.
2. **Parser** (`Parser`): recursive descent con precedence climbing per le espressioni. Produce un AST tipizzato (una classe per ogni tipo di nodo).
3. **Evaluator** (`_Interp`): tree-walking interpreter con catena di ambienti (`Env`) per lo scoping lessicale.

## Scelte di design

- **Scoping lessicale con catena di `Env`**: ogni `{ }` apre un nuovo scope figlio. Le closure catturano l'ambiente per riferimento (l'oggetto `Env` è condiviso), il che rende naturale la semantica di cattura by-reference richiesta dalla spec.
- **Funzioni dichiarate (`fn name(…) { }`)**: equivalenti a `let name = fn(…) { }`. Il body è un `BlockStmt` che crea il suo scope, separato dallo scope dei parametri. Questo permette `let x = …` nel body senza conflitto con un parametro omonimo (shadowing).
- **Segnali di controllo flusso**: `break`, `continue` e `return` usano eccezioni Python (`_SigBreak`, `_SigContinue`, `_SigReturn`) derivate da `BaseException` per propagarsi attraverso blocchi annidati senza complicare ogni livello di esecuzione.
- **Divisione/modulo C-style**: implementata con `abs(a)//abs(b)` e aggiustamento del segno, per evitare problemi di precisione con float e supportare interi arbitrari.
- **`bool` vs `int` in Python**: `bool` è sottoclasse di `int` in Python; ogni controllo di tipo usa `isinstance(v, bool)` prima di `isinstance(v, int)` oppure il metodo `_tname()` per disambiguare.
- **Sentinella `_SENTINEL`**: usata in `Env.get()` per distinguere "variabile non trovata" da "variabile con valore None (nil)".
- **Ricorsione**: `sys.setrecursionlimit(10000)` è impostato temporaneamente in `run()` per supportare ricorsione MiniLang ≥ 200 livelli (ogni livello aggiunge ~6 frame Python).

## Assunzioni

- `int("  42")` con spazi è un errore (la spec dice "stringa di cifre con - opzionale").
- `int("+42")` è un errore (solo `-` è ammesso come segno).
- L'assegnamento a indice su stringhe (`s[0] = "x"`) è un errore runtime (le stringhe non sono liste).
- `fn name(…) { }` come statement non richiede `;` (terminato dal `}`), mentre `fn(…) { }` come espressione in un expression-statement richiede `;`.
- Un `break` o `continue` dentro una funzione definita all'interno di un `while` è un `ParseError` (il contesto loop viene resettato entrando in una funzione).

## Limiti noti

- Nessuna ottimizzazione tail-call: la ricorsione è limitata dallo stack Python (~1500 livelli MiniLang con il limite a 10000).
- Un nuovo `Env` viene creato per ogni esecuzione di blocco, anche quando non ci sono dichiarazioni `let`. Per loop molto stretti questo aggiunge overhead, ma il test con 300.000 iterazioni completa in <1s.

## Testing

104 test con `unittest` / `pytest` in `test_minilang.py`, che coprono:
- Lexer: stringhe, escape, commenti, caratteri non validi
- Aritmetica: divisione/modulo C-style, interi grandi, errori di tipo
- Confronti: tra tipi, uguaglianza strutturale liste, identità funzioni
- Operatori booleani: short-circuit, errori di tipo, condizioni non-bool
- Variabili: scoping, shadowing, ridichiarazione, assegnamento a indefiniti
- Controllo flusso: if/else if/else, while, break, continue
- Funzioni: ricorsione 200, closure by-reference, anonime, IIFE, first-class
- Liste: mutabilità condivisa, indici negativi, assegnamento a indice, push/pop
- Built-in: tutti e 8, inclusi casi limite
- CLI: exit code 1 per errori, exit code 2 per file mancante, output parziale su errore
- Performance: 300.000 iterazioni in <10s
