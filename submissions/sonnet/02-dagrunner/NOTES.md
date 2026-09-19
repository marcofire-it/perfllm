# NOTES — dagrunner

## Design

- **Scheduler a thread singolo coordinatore**: `run()` gira interamente nel thread
  chiamante; è l'unico scrittore delle strutture condivise (`status`, `results`,
  `errors`, `attempts`, `order`, `remaining_deps`, `ready_heap`, `active_count`).
  I thread worker comunicano solo tramite `queue.Queue` (mai scrivono
  direttamente nei dizionari condivisi) → nessuna necessità di lock, nessuna
  race sui dati esposti in `RunResult`.
- **Readiness**: per ogni task si mantiene l'insieme delle dipendenze non ancora
  `success`; quando un task ha successo, viene rimosso dall'insieme dei suoi
  dipendenti e, se l'insieme diventa vuoto, il dipendente entra in uno
  **heap** (min-heap su `(indice_di_inserimento, nome)`), che garantisce che
  tra i task pronti contemporaneamente venga sempre avviato prima quello
  inserito prima (stesso criterio usato in `topological_order`, algoritmo di
  Kahn con tie-break deterministico via heap).
- **Concorrenza**: un contatore `active_count` limita i task realmente in
  esecuzione a `max_workers`; un nuovo task parte solo quando c'è uno slot
  libero e ci sono elementi nello heap. Ogni task, coi suoi eventuali retry,
  occupa un solo "slot" logico per tutta la sua durata (i retry sono
  sequenziali all'interno dello stesso worker thread), coerente con
  "mai più di `max_workers` task in esecuzione contemporaneamente".
- **Timeout**: quando un task ha `timeout` impostato, ogni tentativo viene
  eseguito in un thread dedicato e si attende con `t.join(timeout)`. Se il
  thread è ancora vivo allo scadere, il tentativo è considerato fallito con
  `TimeoutError` (conta come tentativo, si applicano i retry); il thread
  "leaked" continua in background ma il suo eventuale risultato tardivo è
  ignorato (ogni tentativo usa un box/risultato dedicato, catturato per
  valore tramite default-argument per evitare il classico bug di late
  binding delle closure Python nei loop).
- **Propagazione fallimento → skipped**: alla ricezione di un fallimento
  definitivo si fa una visita (DFS/BFS) sul grafo dei "dipendenti" a partire
  dal task fallito, marcando `skipped` tutti i discendenti non ancora
  terminali. Questo avviene **indipendentemente** da `fail_fast`, perché è
  richiesto sempre dalla specifica. Un task marcato `skipped` non può essere
  già `running`/`success` per costruzione: un task entra nello heap solo se
  *tutte* le sue dipendenze sono `success`, quindi non può essere discendente
  di un task fallito (altrimenti una delle sue dipendenze sarebbe `failed`
  o `skipped`, non `success`).
- **`fail_fast=True`**: dopo il primo fallimento definitivo si smette di
  estrarre nuovi task dallo heap (i task già in esecuzione vengono comunque
  attesi fino al loro esito/timeout). Al termine del loop, ogni task rimasto
  senza uno stato assegnato (non avviato, non skippato) viene marcato
  `cancelled`.
- **Nessuna attesa attiva**: lo scheduler si blocca su `queue.Queue.get()`
  (bloccante, senza polling) finché un worker non pubblica un esito.
- **Rieseguibilità**: `run()` non modifica mai lo stato del `DAG` (nomi,
  dipendenze, spec dei task); tutte le strutture mutabili sono locali alla
  chiamata → chiamate multiple producono `RunResult` indipendenti.

## Assunzioni

- `deps` duplicati nella stessa chiamata `add_task` vengono deduplicati
  silenziosamente preservando l'ordine (non specificato esplicitamente dal
  task).
- `name` deve essere una stringa non vuota; non viene fatto alcun `strip()`
  (nomi con soli spazi sono considerati "non vuoti" quindi validi).
- `retries`/`timeout`/`max_workers` con tipo `bool` sono rifiutati esplicitamente
  (in Python `bool` è sottoclasse di `int`, ma non ha senso come valore qui).
- L'eccezione sollevata da un timeout è una `TimeoutError` "sintetica"
  generata dal runner (non proviene dal thread del task), come richiesto
  dalla specifica.
- Quando `fail_fast=True` e un task indipendente dal fallimento era già
  presente nello heap "pronto" ma non ancora avviato al momento del
  fallimento, il suo stato finale è `cancelled` (mai eseguito, `attempts=0`),
  coerente con "i task non avviati che non dipendono dal task fallito hanno
  status = cancelled".
- Un `DAG` vuoto (`run()` senza task) restituisce un `RunResult` con tutti i
  campi vuoti e `ok == True`.

## Limiti noti

- I thread di esecuzione oltre il timeout non vengono interrotti (non
  richiesto dalla specifica): restano "leaked" fino al loro naturale
  completamento; il loro risultato/eccezione viene comunque ignorato.
- La cancellazione (`cancelled`) è calcolata solo a fine esecuzione: non è
  garantito un ordine specifico tra i task `cancelled` (non richiesto dalla
  specifica, che vincola solo `order` per i task effettivamente avviati).

## Come ho testato

`test_dagrunner.py` (solo `unittest`, nessuna dipendenza esterna) copre:
validazioni di `add_task` (nome vuoto, duplicati, `fn` non callable,
`retries`/`timeout` invalidi, dipendenze future); `topological_order`
(dipendenza sconosciuta, ciclo, self-loop, determinismo, nessuna esecuzione);
l'esempio della specifica; DAG vuoto; `max_workers` invalido; nessuna
esecuzione se il grafo non è valido; il dizionario `deps` passato a `fn`
contiene solo ed esattamente le dipendenze dirette; rieseguibilità;
rispetto del limite `max_workers` sotto carico concorrente (con contatore
protetto da lock e `sleep`); retry (successo dopo N fallimenti, esaurimento
retry); timeout (fallimento entro il tempo previsto, valore tardivo
ignorato); propagazione `skipped` e differenza `fail_fast=True/False`;
`cancelled` per task indipendenti mai avviati con `max_workers=1`; ordine di
avvio (`order`) nel caso di dipendenze a ventaglio.

Eseguito anche uno stress test manuale (50 task, dipendenze casuali,
fallimenti casuali, `max_workers=1`) per verificare l'assenza di deadlock e
la coerenza degli stati finali (`cancelled`/`failed`/`skipped`/`success`).

Comando: `python -m unittest test_dagrunner.py -v` → 27 test, tutti OK.
