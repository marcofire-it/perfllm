# NOTES — task 02 `dagrunner`

## Scelte di design

- **Architettura scheduler/worker**: `run()` valida il grafo, poi avvia un pool di
  `max_workers` thread worker su una coda `queue.deque`, sincronizzati con un unico
  `threading.Condition` (nessun busy-wait). Il thread chiamante fa da scheduler:
  avvia i task pronti (heapq su indice di inserimento ⇒ ordine deterministico)
  solo se `in_flight < max_workers`, quindi attende notifiche di completamento.
  Questo garantisce che non ci siano mai più di `max_workers` task in esecuzione.
- **Timeout**: ogni tentativo esegue la `fn` in un sotto-thread demone con
  `join(timeout)`. Se scade, il tentativo conta come fallito con `TimeoutError`
  (builtin); il thread è lasciato in esecuzione (la spec non richiede di
  interromperlo) e il suo eventuale risultato viene ignorato. Essendo demone,
  non blocca l'uscita dell'interprete.
- **Retry**: gestiti dentro il worker (fino a `retries + 1` esecuzioni); lo
  scheduler vede solo l'esito finale. `attempts` riporta il numero di tentativi
  realmente effettuati (1 al momento dell'avvio, aggiornato al completamento).
- **`topological_order()`**: Kahn con heap sugli indici di inserimento, così tra i
  task contemporaneamente disponibili vince sempre quello aggiunto per primo
  (casi tipo: `a`, `c←a`, `b` ⇒ ordine `a, c, b`).
- **Propagazione/fail_fast**: al primo fallimento definitivo i dipendenti
  transitivi diventano `skipped`; con `fail_fast=True` gli altri task pendenti
  diventano `cancelled` e non se ne avvia più nessuno (chi è già in esecuzione
  viene atteso). Con `fail_fast=False` i task indipendenti proseguono e ogni
  fallimento successivo propaga i propri `skipped`.

## Assunzioni

- `name` e ogni elemento di `deps` devono essere stringhe non vuote, altrimenti
  `ValueError` (la spec parla di "nomi").
- `retries` e `max_workers` devono essere `int` (i `bool` sono rifiutati);
  `timeout` accetta `int`/`float` > 0 oppure `None`.
- Con `fail_fast=True`, se un task indipendente è già **avviato** prima del
  primo fallimento, viene atteso e può finire `success` (la spec prevede di
  attendere i task in esecuzione); `cancelled` si applica solo ai non avviati.
- Dipendenze duplicate in `deps` sono tollerate e trattate come una sola.
- `RunResult` è una classe semplice con i 5 attributi richiesti + proprietà `ok`;
  `ok` è `True` anche per un DAG vuoto.

## Limiti noti

- Un `fn` che ignora il timeout e resta bloccato continua a girare in un thread
  demone anche dopo il ritorno di `run()` (comportamento ammesso dalla spec).
- L'ordine topologico è O(n log n); la scansione di terminazione in `run()` è
  O(n) per evento, sufficiente per DAG di dimensioni realistiche.

## Test

- `test_dagrunner.py`: 33 test unittest (esempio della spec, validazioni,
  ordine deterministico, retry, timeout, propagazione, fail_fast on/off,
  riesecuzione, rispetto di `max_workers`, stress a 100 task). Tutti verdi con
  `python -m unittest test_dagrunner` (Python 3.12).
- Stress extra: 200 DAG casuali con fallimenti casuali e `max_workers`
  variabili, verificando invarianti di stato, `order`, `attempts` e `ok`.
