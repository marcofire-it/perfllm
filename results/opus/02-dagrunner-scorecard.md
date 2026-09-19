# Scorecard — modello: `opus` · task: `02-dagrunner` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `42/42` → core `28/28`, edge `9/9`, perf `5/5`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (eccezioni, `RunResult` con i 5 attributi + `ok`, `DAG.add_task/topological_order/run` con firme esatte)
- Dipendenze esterne / costrutti vietati: nessuna (heapq, queue, threading, collections). Nessun print, nessun busy-wait (coordinatore bloccato su `queue.get()`).
- Formato consegna (file integrali, NOTES.md): ok (`dagrunner.py`, `NOTES.md`, `test_dagrunner.py`)
- Deviazioni non documentate: il vincolo "mai più di `max_workers` task in esecuzione contemporanea" viene violato con timeout + retry: il tentativo scaduto continua a girare nel thread helper (`_execute_with_timeout`, riga 107) mentre il worker avvia subito il tentativo successivo. Misurato: 4 esecuzioni concorrenti di `fn` con `max_workers=1`, `timeout=0.1`, `retries=3`. NOTES.md ammette i thread pendenti ma non l'effetto sul limite di concorrenza. Deviazione minore (-1).
- **B = 14/15**

## C. Qualità del codice (15)
- Struttura: separazione netta tra registrazione, Kahn (`topological_order`) ed esecuzione; scheduler a singolo scrittore nel thread chiamante, i worker comunicano solo via coda. Helper `_execute_with_timeout` isolato e leggibile. Type hint completi, docstring utili.
- Gestione errori / thread / risorse: cattura `BaseException` nei worker con "safety net" che garantisce sempre un messaggio in coda (nessun deadlock possibile); thread daemon; validazione input completa. Propagazione skipped/cancelled gestita con cura (un task `cancelled` che dipende da un secondo fallimento viene promosso a `skipped`, righe 318-325).
- Punti di forza: loop di coordinamento compatto (righe 269-338) e facilmente verificabile; dedup delle dipendenze preservando l'ordine.
- Punti deboli: docstring di `RunResult` dice "Immutable" ma non lo è; commento morto alle righe 327-329 che descrive un'operazione non eseguita; `run()` è una funzione di ~150 righe con closure interna, avrebbe giovato di un'estrazione (stato di run in una classe privata).
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| `fn` che solleva `KeyboardInterrupt` / `SystemExit` | run() non crasha, task `failed` con l'eccezione registrata | `failed` con `KeyboardInterrupt` / `SystemExit` in `errors`, altri task `success` | ok |
| 2000 task indipendenti, `max_workers=8` | completa in tempi/memoria ragionevoli | 0.25 s, picco 0.9 MB, nessun thread residuo | ok |
| task in timeout che ritorna "LATE" dopo 0.6 s con un dipendente | dipendente `skipped`, nessun risultato stale usato | `slow: failed (TimeoutError)`, `dep: skipped`, `fn` del dipendente mai chiamata | ok |
| `run()` due volte con `fail_fast` diverso, `max_workers=1` | risultati indipendenti e coerenti | `ind: cancelled` poi `ind: success`, oggetti distinti | ok |
| deps come set / tuple / generatore | accettati | tutti `success` | ok |
| catena di 1500 task, `max_workers=1` | nessuna RecursionError, `order` = catena | ok in 0.12 s, order corretto | ok |
| `fn` che modifica il dict `deps` ricevuto | il risultato originale del dep non cambia | `results["a"]` intatto | ok |
| timeout 0.1 + retries 3 con `max_workers=1` | max 1 `fn` in esecuzione | picco 4 esecuzioni concorrenti (thread scaduti ancora vivi) | ko (minore) |
| uscita del processo con thread in timeout che dorme 3 s | uscita immediata | immediata (thread daemon) | ok |
- **D = 9/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, chiaro e onesto: design, assunzioni numerate (bool accettato come int, coerente col codice), limiti noti (thread pendenti, KeyboardInterrupt trattato come fallimento).
- Assunzioni dichiarate coerenti con il codice: sì
- Test propri: buoni (51 test `unittest`, tutti verdi in 5.7 s con pytest): validazioni, Kahn con tie-break, retry, timeout, skipped vs cancelled, concorrenza misurata, deadlock con un solo worker, fan-out 50, deps come set.
- **E = 5/5**

## Totale: **96 / 100**

## Commento
Consegna solida e aderente. Ha gestito tutte le trappole elencate in TRAPS.md: validazione prima di ogni esecuzione, `retries` come ritentativi aggiuntivi, distinzione skipped/cancelled, task in corso attesi con fail_fast, ordine deterministico con heap sull'indice di inserimento, nessun busy-wait, nessun deadlock con un solo worker, `run()` rieseguibile. La scelta di un thread per task (senza pool) è semplice e funziona bene anche a 2000 task.
L'unica ombra è la semantica del timeout: la spec ammette di non uccidere il thread, ma l'implementazione riparte subito col tentativo successivo mentre il precedente gira ancora, quindi sotto timeout+retry la concorrenza reale supera `max_workers`. È lo stesso comportamento delle altre due consegne. Nel NOTES lo accenna senza trarne la conseguenza.
Usabile in produzione così com'è per DAG di piccola/media taglia; la suite di test propria è la più ampia delle tre.
