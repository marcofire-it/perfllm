# NOTES — minilang.py

## Architettura
Pipeline classica: `tokenize()` (lexer) → `Parser` (recursive descent, produce
un AST di classi con `__slots__`) → `Interpreter` (tree-walking, esegue
statement/espressioni). `run(source)` orchestra le tre fasi, cattura l'output
in una lista di stringhe (nessun redirect di `sys.stdout`) e in caso di
eccezione popola `err.output` prima di rilanciare.

Valori runtime mappati su tipi Python nativi: `int` (precisione arbitraria
nativa), `bool`, `str`, `list` (mutabile, condivisa per riferimento — le
liste non vengono mai copiate se non con `+` che crea una nuova lista),
`None` per `nil`, `MiniFunction`/`BuiltinFunction` per le funzioni.
Il controllo di tipo usa sempre `type(x) is ...` (mai `isinstance`) perché in
Python `bool` è sottoclasse di `int`: questo garantisce che `1 == true` sia
`false` e che `-` unario rifiuti i bool.

Scoping lessicale con `Env` (dict + puntatore al parent). Ogni `{ }` eseguito
come corpo di `if`/`else`/`while`/blocco standalone crea un nuovo `Env`
figlio; una chiamata di funzione crea un unico nuovo `Env` (figlio della
closure) in cui vengono legati i parametri e poi eseguito direttamente il
corpo (nessuno scope aggiuntivo), il che permette il pattern
"contatore/closure" dell'esempio. Le funzioni catturano l'oggetto `Env` per
riferimento, quindi la ricorsione funziona perché il nome della funzione
viene scritto nello stesso `Env` già catturato dalla chiusura.

`break`/`continue`/`return` sono implementati con eccezioni interne
(`BreakSignal`, `ContinueSignal`, `ReturnSignal`), non propagate al chiamante
di `run()`.

## Assunzioni / interpretazioni scelte
- **`break`/`continue` attraverso confini di funzione**: il parser resetta il
  contatore di "dentro un while" a 0 quando entra nel corpo di una `fn`
  (dichiarata o anonima), quindi `while (true) { fn f() { break; } }` è
  `ParseError` (il `break` non è lessicalmente dentro un while all'interno
  della stessa funzione). Sembra la lettura più coerente con la semantica
  "solo dentro un while" e coerente col comportamento runtime (altrimenti un
  `break` eseguito fuori dal frame del while attivo propagherebbe come
  eccezione Python non gestita).
- **Target di assegnamento**: oltre a `x = expr;` e `xs[i] = expr;` è
  supportato anche l'annidamento `xs[i][j] = expr;` (qualunque catena
  postfissa che termina in un indice), per generalità; assegnare a un target
  che non sia `Name` o `Index` (es. una chiamata) è `ParseError`.
- **Shadowing dei builtin**: i builtin (`print`, `len`, ...) vivono come
  variabili ordinarie nello scope globale; ridichiararli con `let` nello
  stesso scope globale è quindi un errore di "già dichiarata" come per
  qualunque altro nome, mentre in uno scope annidato lo shadowing funziona
  normalmente (è quanto richiesto dal task).
- **Messaggi di errore**: il testo esatto dei messaggi non è specificato dal
  task (solo il formato `ParseError: line N: <messaggio>` /
  `RuntimeError: line N: <messaggio>` per la CLI); ho scelto messaggi in
  italiano, descrittivi, non verificati da alcun test automatico noto.
- **`int(s)`**: accetta solo stringhe che matchano interamente
  `-?[0-9]+` (nessuno spazio iniziale/finale ammesso); su altri formati
  solleva `MiniRuntimeError`.
- **Limite di ricorsione Python**: `run()` alza temporaneamente
  `sys.setrecursionlimit` (ripristinato in un blocco `finally`) per
  supportare la ricorsione MiniLang fino a profondità 200 richiesta, dato che
  ogni livello di ricorsione MiniLang corrisponde a diversi frame Python
  nell'interprete a tree-walking.
- **File mancante da CLI**: se il file passato a `python minilang.py <file>`
  non esiste (o non è leggibile), si esce con codice `2` senza messaggio
  aggiuntivo su stderr (il task specifica solo il codice di uscita).
  Se manca l'argomento del file, uscita con codice `2` e un breve messaggio
  d'uso su stderr (comportamento non specificato dal task, scelto per
  ragionevolezza).

## Limiti noti
- I messaggi di errore non sono in un formato "ufficiale" (solo prefisso e
  riga sono garantiti dal task).
- Non è implementato alcun limite alla profondità di ricorsione oltre a
  quanto imposto da Python stesso (`RecursionError` viene convertita in
  `MiniRuntimeError` con riga `0` come fallback estremo, ma non dovrebbe mai
  scattare entro i limiti richiesti dal task).

## Come è stato testato
- Eseguito l'esempio del task via CLI (`python minilang.py`), output
  verificato carattere per carattere contro i commenti del task.
- `test_minilang.py` (35 test `unittest`, solo libreria standard) copre:
  aritmetica con troncamento/segno, interi arbitrariamente grandi,
  concatenazione stringhe/liste, riferimenti condivisi delle liste,
  rappresentazione testuale annidata, uguaglianza strutturale e per tipi
  diversi, short-circuit di `and`/`or`, indicizzazione negativa su
  stringhe/liste, closure che catturano per riferimento, ricorsione a
  profondità 200, scoping/shadowing, funzioni senza `return`, builtin
  (`range`, `len`, `int`, `push`, `pop`), ed errori di parsing/runtime
  (compreso il recupero dell'output parziale in `err.output` e la
  correttezza della riga riportata per errori dentro una funzione).
- Verificato manualmente un `while` da 300 000 iterazioni: tempo di
  esecuzione ≈ 0.8 s (ben sotto il limite di 10 s richiesto).
- Verificato `python -c "from minilang import run"` senza effetti
  collaterali e senza eseguire `main()`.
