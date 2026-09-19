# NOTES — MiniLang (task 03)

## Cosa è stato consegnato
- `minilang.py`: lexer + parser (recursive descent) + interprete tree-walking, sola libreria standard.
  API pubblica: `run`, `MiniLangError`, `ParseError`, `MiniRuntimeError`; CLI `python minilang.py <file>`
  (exit 0 ok, 1 errore di programma con output parziale su stdout e `ParseError|RuntimeError: line N: msg`
  su stderr, 2 file assente/uso errato).
- `test_minilang.py`: 22 test `unittest` (tutti verdi, ~0.7 s), inclusi esempio del task, chiusura di
  scope, short-circuit, big int, ricorsione a 200/500 e benchmark dei 300.000 iterazioni.
- `example.ml`: l'esempio del task (usato per il smoke test della CLI).

## Scelte di design
- AST a tuple `(tag, ..., line)`: ultimo elemento sempre la riga 1-based del token che ha causato
  l'errore; per i binari la riga è quella dell'operatore.
- Environment a dict con puntatore al padre; le funzioni catturano l'ambiente (closure per riferimento);
  ogni `{ }` (inclusi corpi di `if`/`while` e corpo di funzione) apre uno scope nuovo a ogni esecuzione.
- Controllo di flusso (`break`/`continue`/`return`) con eccezioni interne Python; i built-in sono oggetti
  nel scope globale, shadowabili negli scope interni (ma `let print = ...` a livello top è ridichiarazione
  nello stesso scope ⇒ errore runtime, coerente con la regola di scoping).
- `/` e `%` implementati con aritmetica intera (troncamento verso zero, segno del dividendo), quindi
  corretti anche con interi di precisione arbitraria (nessuna conversione a float).
- `and`/`or` verificano che **entrambi** gli operandi siano `bool` (l'operando destro solo se valutato).
- `run()` alza `sys.setrecursionlimit` a 20000 se necessario: la ricorsione MiniLang a 200+ livelli
  supera il limite Python di default (1000) perché ogni chiamata MiniLang usa più frame Python. È
  l'unico effetto collaterale di `run()`; l'import di `minilang` non ha effetti collaterali.

## Assunzioni / interpretazioni
- `xs[i] = e`: il task mostra solo `ident[i]`; ho comunque supportato catene di indicizzazione
  (`a[0][1] = e`) valutando gli indici da sinistra a destra. Assegnare in una stringa (anche via catena)
  è errore runtime.
- Parametri duplicati in una firma (`fn f(a, a)`) ⇒ errore runtime alla chiamata (stessa regola di
  `let` nello stesso scope); non è coperto esplicitamente dal task.
- Errore di arità dei built-in: trattata come "tipi o arità sbagliati" ⇒ errore runtime.
- `str`/`print` di stringhe dentro liste: virgolette senza escape dei caratteri interni, come da specifica.
- `int("007")` → 7 (zeri iniziali ammessi); `int` accetta solo `[0-9]+` con `-` opzionale.
- Se il file non esiste o l'argomento manca, la CLI esce con codice 2 (il task specifica solo il file
  assente; ho uniformato).

## Limiti noti
- Prestazioni: interprete tree-walking; il benchmark richiesto (300.000 iterazioni con due operazioni)
  completa in ~0.7 s su questa macchina, ben sotto i 10 s. Programmi ricorsivi molto profondi (> ~5000)
  potrebbero comunque incontrare il limite di ricorsione Python.
- Messaggi di errore: la forma esatta del testo non è prescritta dal task, solo il prefisso
  `ParseError`/`RuntimeError`, la riga e il formato `line N: <messaggio>`.

## Come ho testato
`python -m unittest test_minilang` (22 test, tutti passanti) + esecuzioni CLI manuali di `example.ml`
(output identico a quello atteso nel task), di programmi con errore runtime/parse (verifica di output
parziale su stdout, messaggio su stderr, codici d'uscita 1 e 2) e del benchmark delle 300.000 iterazioni.
