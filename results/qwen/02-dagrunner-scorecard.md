# Scorecard — modello: `qwen` · task: `02-dagrunner` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `42/42` → core `28/28`, edge `9/9`, perf `5/5`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (eccezioni, `RunResult` con i 5 attributi + `ok` e `__repr__`, firme esatte; `__all__` esplicito)
- Dipendenze esterne / costrutti vietati: nessuna (heapq, threading, collections). Nessun print, nessun busy-wait (`Condition.wait()`).
- Formato consegna (file integrali, NOTES.md): ok (`dagrunner.py`, `NOTES.md`, `test_dagrunner.py`)
- Deviazioni non documentate: (1) con timeout + retry il tentativo scaduto resta in esecuzione (riga 264) mentre parte il successivo: misurate 4 esecuzioni concorrenti di `fn` con `max_workers=1`, `timeout=0.1`, `retries=3`. NOTES.md afferma esplicitamente che il design "garantisce che non ci siano mai più di `max_workers` task in esecuzione", affermazione smentita in questo caso. (2) NOTES.md dichiara che le dipendenze duplicate sono "trattate come una sola", ma `add_task` non deduplica (riga 127): funziona per caso perché in-degree e decrementi si compensano. Deviazioni minori ma dichiarate in modo inesatto (-2).
- **B = 13/15**

## C. Qualità del codice (15)
- Struttura: architettura pool di `max_workers` worker + `Condition` unica + scheduler nel thread chiamante. Design legittimo ma più complesso del necessario: tre livelli di thread (worker del pool, più un thread `_run` per **ogni** tentativo anche quando `timeout` è `None`, righe 258-267), quindi due thread per ogni esecuzione. Validazione input la più completa delle tre (controlla anche il tipo degli elementi di `deps`).
- Gestione errori / thread / risorse: `BaseException` catturata; thread daemon; worker chiusi correttamente con `shutdown` + `notify_all` + `join`. **Bug latente**: in `on_failure` (riga 245) `stop_launching = True` assegna una variabile locale perché manca `nonlocal`; il flag esterno resta sempre `False`. Il fail-fast funziona lo stesso solo perché la stessa funzione marca subito `cancelled` tutti i task pendenti (righe 246-248), rendendo il flag inutile: codice morto che maschera un errore. Il test di terminazione `all(state[n] in terminal for n in names)` (riga 332) è O(n) per ogni evento, quindi O(n²) complessivo.
- Punti di forza: `RunResult` copia le strutture (isolamento dal runner); docstring e `__all__`; validazione rigorosa.
- Punti deboli: bug `nonlocal` mascherato; doppio thread per esecuzione senza motivo; scan O(n) per evento; `attempts[name] = 1` impostato all'avvio e poi sovrascritto (ridondante).
- **C = 10/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| `fn` che solleva `KeyboardInterrupt` / `SystemExit` | run() non crasha, task `failed` con l'eccezione registrata | `failed` con `KeyboardInterrupt` / `SystemExit` in `errors`, altri task `success` | ok |
| 2000 task indipendenti, `max_workers=8` | completa in tempi/memoria ragionevoli | 0.24 s, picco 0.7 MB, nessun thread residuo | ok |
| task in timeout che ritorna "LATE" dopo 0.6 s con un dipendente | dipendente `skipped`, nessun risultato stale usato | `slow: failed (TimeoutError)`, `dep: skipped`, `fn` del dipendente mai chiamata | ok |
| `run()` due volte con `fail_fast` diverso, `max_workers=1` | risultati indipendenti e coerenti | `ind: cancelled` poi `ind: success`, oggetti distinti | ok |
| deps come set / tuple / generatore | accettati | tutti `success` | ok |
| catena di 1500 task, `max_workers=1` | nessuna RecursionError, `order` = catena | ok in 0.21 s, order corretto | ok |
| `fn` che modifica il dict `deps` ricevuto | il risultato originale del dep non cambia | `results["a"]` intatto | ok |
| `retries=True`, `max_workers=True` | comportamento coerente | `ValueError` esplicito per entrambi | ok |
| timeout 0.1 + retries 3 con `max_workers=1` | max 1 `fn` in esecuzione | picco 4 esecuzioni concorrenti (thread scaduti ancora vivi) | ko (minore) |
| uscita del processo con thread in timeout che dorme 3 s | uscita immediata | immediata (thread daemon) | ok |
- **D = 9/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente e ben organizzato (design, assunzioni, limiti, test), ma contiene due affermazioni non vere sul codice (garanzia su `max_workers`, dedup delle dipendenze).
- Assunzioni dichiarate coerenti con il codice: parzialmente (vedi sopra)
- Test propri: buoni (33 test `unittest`, tutti verdi in 2.7 s con pytest): validazioni, ordine deterministico, retry, timeout con successo al secondo tentativo, propagazione, fail_fast on/off, rispetto di `max_workers`, deadlock con un worker, stress a 100 task.
- **E = 4/5**

## Totale: **91 / 100**

## Commento
Funzionalmente equivalente alle altre due consegne (42/42 nei test nascosti, identico comportamento in tutte le prove manuali), ma con un'implementazione più macchinosa e meno curata. Ha gestito le trappole principali di TRAPS.md (validazione prima di eseguire, skipped vs cancelled, attesa dei task in corso, Kahn deterministico, nessun busy-wait, nessun deadlock, rieseguibilità).
Il difetto più serio è il `nonlocal` mancante su `stop_launching`: il flag che dovrebbe fermare gli avvii non viene mai impostato e il fail-fast regge solo grazie a un secondo meccanismo (marcatura `cancelled`). Un bug che i test non vedono e che diventerebbe un problema alla prima modifica. Il thread aggiuntivo per ogni tentativo anche senza timeout raddoppia i thread creati senza vantaggi.
NOTES.md è scritto bene ma promette più di quello che il codice mantiene. Usabile, ma richiederebbe una passata di pulizia prima di andare in produzione.
