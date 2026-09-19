# NOTES — dagrunner

## Scelte di design

### Scheduling
- La coordinazione avviene nel thread principale tramite una `queue.Queue` (nessun busy-wait).
  I worker-thread inviano un messaggio di completamento sulla coda; il main thread blocca su `queue.get()`.
- I task pronti vengono mantenuti in un **min-heap** con chiave sull'indice di inserimento, 
  garantendo il tie-breaking deterministico richiesto dalla specifica (ordine di inserimento).

### Timeout
- Se `timeout` è impostato, `fn` viene eseguita in un daemon thread separato; il worker attende
  un `threading.Event` con timeout. Se l'evento non viene segnalato entro il timeout, viene
  sollevato `TimeoutError` (che conta come tentativo e i retry si applicano).
- Il daemon thread continua a girare dopo il timeout (la specifica lo consente: "Non è richiesto
  interrompere il thread"). Il valore eventualmente restituito viene ignorato.

### Retry
- I retry avvengono all'interno dello stesso worker-thread. Non viene rilasciato lo slot di
  concorrenza tra un tentativo e l'altro (stessa semantica di "un task in esecuzione").

### fail_fast
- Dopo il primo fallimento definitivo, `stop_new = True` impedisce l'avvio di nuovi task.
- I task non avviati che dipendono (transitivamente) da un task fallito → **skipped**.
- I task non avviati indipendenti dal fallimento → **cancelled**.
- Se un secondo task già in esecuzione fallisce, i suoi dipendenti transitivi passano da
  "cancelled" a "skipped" (la relazione di dipendenza ha priorità).

### Deduplicazione deps
- Eventuali dipendenze duplicate vengono rimosse in `add_task` mantenendo l'ordine di prima
  occorrenza (`dict.fromkeys`).

## Assunzioni

1. `retries` deve essere un `int` (non un float che rappresenta un intero); `bool` è accettato 
   perché è sottoclasse di `int`.
2. `timeout` accetta sia `int` che `float`.
3. Un DAG vuoto (nessun task) è valido e `run()` restituisce `RunResult` con `ok == True`.
4. `topological_order()` è idempotente e non modifica lo stato del DAG.
5. L'ordine di `order` riflette l'ordine di **primo avvio** di ogni task, non l'ordine di completamento.

## Limiti noti

- I daemon thread generati per gestire i timeout non vengono terminati: task con timeout molto
  brevi e molti retry possono accumulare thread pendenti. Questo è accettabile per la specifica.
- Non viene gestito `KeyboardInterrupt` in modo speciale: se catturato dentro un worker, viene
  trattato come un fallimento ordinario del task.

## Testing

51 test con `unittest`, eseguibili con `python -m pytest test_dagrunner.py -v`:

- Gerarchia eccezioni, validazione parametri `add_task`
- `topological_order`: catena lineare, diamond, forward reference, self-loop, ciclo, ordine deterministico
- `run`: esempio della specifica, DAG vuoto, singolo task, validazione `max_workers`, graph validation pre-esecuzione, rieseguibilità
- Retry: successo al terzo tentativo, fallimento totale, zero retry
- Timeout: fallimento, timeout + retry, task veloce con timeout impostato
- Propagazione fallimenti: skipped diretto, skipped transitivo, indipendenti con `fail_fast=False`
- `fail_fast=True`: cancellazione indipendenti, distinzione skipped/cancelled, completamento task già in esecuzione
- Concorrenza: speedup parallelo, rispetto limite `max_workers`, singolo worker
- Edge case: deadlock con `max_workers=1`, fan-out 50 task, deps come set, fn che restituisce `None`
