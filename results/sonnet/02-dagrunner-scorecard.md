# Scorecard — modello: `sonnet` · task: `02-dagrunner` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `42/42` → core `28/28`, edge `9/9`, perf `5/5`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (eccezioni, `RunResult` dataclass con i 5 attributi + `ok`, firme esatte di `add_task`/`topological_order`/`run`)
- Dipendenze esterne / costrutti vietati: nessuna (heapq, queue, threading, dataclasses). Nessun print, nessun busy-wait (coordinatore bloccato su `queue.get()`).
- Formato consegna (file integrali, NOTES.md): ok (`dagrunner.py`, `NOTES.md`, `test_dagrunner.py`)
- Deviazioni non documentate: con timeout + retry il tentativo scaduto continua nel thread helper (riga 202) mentre il worker avvia subito il successivo: misurate 4 esecuzioni concorrenti di `fn` con `max_workers=1`, `timeout=0.1`, `retries=3`, contro il vincolo "mai più di `max_workers`". NOTES.md dichiara i thread "leaked" ma sostiene che ogni task occupa un solo slot logico, senza notare l'effetto sul limite reale. Deviazione minore (-1).
- **B = 14/15**

## C. Qualità del codice (15)
- Struttura: la più compatta delle tre (285 righe) senza perdere chiarezza: `_build_graph` riusato da `topological_order` e `run`, scheduler a singolo scrittore, worker che comunicano solo via coda. `RunResult` come dataclass è la scelta più pulita. Type hint e commenti mirati.
- Gestione errori / thread / risorse: `BaseException` catturata nel thread di esecuzione e nel worker; thread daemon; validazione input completa e rigorosa (rifiuta anche i `bool`). Late-binding delle closure evitato esplicitamente con default-argument (riga 195). Propagazione skipped in `propagate_skip`, cancelled a fine loop.
- Punti di forza: invariante "solo il coordinatore scrive le strutture condivise" rispettato e spiegato; codice facile da verificare a mano.
- Punti deboli: `worker` legge `results` dal thread worker (riga 178) invece di ricevere lo snapshot già pronto dal coordinatore, in contrasto con l'invariante dichiarato (innocuo in pratica, ma è una crepa nel design); il corpo di `worker` con il ramo timeout/no-timeout è un po' intrecciato (`continue`/`break` misti); stato interno `"running"` che sporca il dizionario `status` fino alla copia finale.
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| `fn` che solleva `KeyboardInterrupt` / `SystemExit` | run() non crasha, task `failed` con l'eccezione registrata | `failed` con `KeyboardInterrupt` / `SystemExit` in `errors`, altri task `success` | ok |
| 2000 task indipendenti, `max_workers=8` | completa in tempi/memoria ragionevoli | 0.25 s, picco 1.1 MB, nessun thread residuo | ok |
| task in timeout che ritorna "LATE" dopo 0.6 s con un dipendente | dipendente `skipped`, nessun risultato stale usato | `slow: failed (TimeoutError)`, `dep: skipped`, `fn` del dipendente mai chiamata | ok |
| `run()` due volte con `fail_fast` diverso, `max_workers=1` | risultati indipendenti e coerenti | `ind: cancelled` poi `ind: success`, oggetti distinti | ok |
| deps come set / tuple / generatore | accettati | tutti `success` | ok |
| catena di 1500 task, `max_workers=1` | nessuna RecursionError, `order` = catena | ok in 0.12 s, order corretto | ok |
| `fn` che modifica il dict `deps` ricevuto | il risultato originale del dep non cambia | `results["a"]` intatto | ok |
| `retries=True`, `max_workers=True` | comportamento coerente | `ValueError` esplicito per entrambi | ok |
| timeout 0.1 + retries 3 con `max_workers=1` | max 1 `fn` in esecuzione | picco 4 esecuzioni concorrenti (thread scaduti ancora vivi) | ko (minore) |
| uscita del processo con thread in timeout che dorme 3 s | uscita immediata | immediata (thread daemon) | ok |
- **D = 9/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, il più approfondito dei tre: spiega gli invarianti del design, perché lo skip è sempre corretto per costruzione, le assunzioni (dedup deps, nomi di soli spazi validi, bool rifiutati) e i limiti. Cita anche uno stress test manuale con 50 task casuali.
- Assunzioni dichiarate coerenti con il codice: sì
- Test propri: buoni (27 test `unittest`, tutti verdi in 0.5 s con pytest): meno numerosi degli altri ma mirati sulle parti difficili (nessuna esecuzione su grafo invalido, sole dipendenze dirette, limite `max_workers` misurato con lock, valore tardivo ignorato, cancelled con un solo worker, ordine di avvio).
- **E = 5/5**

## Totale: **96 / 100**

## Commento
Consegna aderente ed essenziale: stesso design di fondo di opus (coordinatore + coda) ma con meno codice e un NOTES.md che dimostra di aver capito il perché delle scelte, non solo il cosa. Tutte le trappole di TRAPS.md sono gestite: validazione prima di eseguire, retry come ritentativi aggiuntivi, skipped vs cancelled, attesa dei task in corso, Kahn deterministico, nessun busy-wait, nessun deadlock, rieseguibilità.
Il limite condiviso con le altre due consegne è la concorrenza sotto timeout+retry, dove i thread scaduti restano vivi mentre parte il tentativo successivo. Piccola incoerenza tra l'invariante dichiarato ("i worker non toccano le strutture condivise") e la lettura di `results` dentro il worker.
Usabile in produzione così com'è per DAG di piccola/media taglia.
