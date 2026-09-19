# Scorecard — modello: `sonnet` · task: `01-logstats` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `34/34` → core `17/17`, edge `16/16`, perf `1/1`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`logstats.py`, opzioni esatte, chiavi JSON esatte, exit code 0/1/2, `--level` validato con `choices`)
- Dipendenze esterne / costrutti vietati: nessuna (solo stdlib)
- Formato consegna (file integrali, NOTES.md): ok (logstats.py, NOTES.md, test_logstats.py)
- Deviazioni non documentate: nessuna. Documentate: k=v solo se chiave e valore entrambi non vuoti (`y=` resta nel template), primo `latency_ms=` valido se ce ne sono più di uno, `errors="replace"` in lettura
- **B = 15/15**

## C. Qualità del codice (15)
- Struttura: la migliore delle tre. `parse_line` restituisce esplicitamente tre esiti (ignora / malformata / ok), `process(fileobj, ...)` è pura e testabile senza subprocess, `main(argv=None)` separato, `build_parser()` isolato. Costanti e regex in testa al file.
- Gestione errori / risorse: `OSError` catturato sia in apertura (exit 2, riga 222) sia durante la lettura (riga 229); `errors="replace"` evita crash su byte non UTF-8. Manca invece la difesa in uscita: `json.dumps(..., ensure_ascii=False)` (riga 233) stampato con `print` su una console cp1252 fa crashare lo script con caratteri non latini (o con il carattere di sostituzione U+FFFD prodotto proprio da `errors="replace"`).
- Punti di forza: leggibilità, separazione delle responsabilità, validazione compatta degli argomenti, template e latenza calcolati in un unico passaggio sui token.
- Punti deboli: guardia morta `if idx < 1` (riga 169: `ceil(0.95*n)` è ≥ 1 per n ≥ 1); `ensure_ascii=False` senza gestire l'encoding di stdout.
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| File con BOM UTF-8 | prima riga malformata o valida | prima riga malformata (total 1, malformed 1) | ok |
| Messaggio unicode (`Ciao è mondo 日本`) + 20 token k=v, console cp1252 | JSON con template corretto | `UnicodeEncodeError`, traceback, exit 1, stdout vuoto | ko |
| `--since` dopo `--until` | total 0, null, exit 0 | corretto | ok |
| File vuoto | total 0, malformed 0, exit 0 | corretto | ok |
| `--top 100000` | 1 voce | 1 voce, count 5 | ok |
| Timestamp con secondi frazionari | riga malformata | malformed 1, total 1 | ok |
| `latency_ms=99999999999999999999` | int esatti, avg float | min/max/p95 esatti, avg `1e+20` | ok |
| 5 righe identiche | total 5, first==last | corretto | ok |
| Righe CRLF | total 2, template `GET /` | corretto | ok |
| Byte non UTF-8 (`caf\xe9`), console cp1252 | nessun crash | decodifica ok grazie a `errors="replace"`, ma poi crash in stampa del carattere U+FFFD (traceback, exit 1). Con console UTF-8 funziona | ko (parziale) |
| `--top abc` | exit 1, stdout vuoto | exit 1, stdout vuoto | ok |
| `--foo` | exit 1 | exit 1 | ok |
| Directory al posto del file | exit 2 | exit 2 | ok |
| `request-id=abc =x y= a=b=c` | k=v rimossi | template `GET =x y= done` (`y=` mantenuto, come documentato) | ok |
- Un'unica classe di cedimento (encoding di stdout su Windows), ma con traceback e senza output; su console UTF-8 tutto passa.
- **D = 5/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, il più dettagliato dei tre: spiega ogni scelta (split con `maxsplit=3`, definizione di k=v, primo `latency_ms`, exit code), assunzioni e limiti reali, misura di performance su 1M righe
- Assunzioni dichiarate coerenti con il codice: sì (verificate `is_kv_token`, primo latency, `errors="replace"`)
- Test propri: buoni (13 test `unittest` via subprocess, passano tutti; esempi del task, exit code, filtri inclusivi, ordinamento, template vuoto, p95)
- **E = 5/5**

## Totale: **93 / 100**

## Commento
Consegna corretta al 100% e la più curata come struttura: `process()` puro, esiti espliciti dal parser di riga, gestione degli errori di I/O completa, NOTES.md esemplare. Ha gestito tutte le trappole di TRAPS.md, compreso `--top abc` con exit 1 e il template vuoto. L'unico difetto reale è lo stesso di opus, in forma più lieve: `ensure_ascii=False` in stampa senza curarsi dell'encoding della console, quindi su Windows un log con caratteri non latini fa crashare lo script (senza però sporcare stdout). È ironico che `errors="replace"`, messo per robustezza, produca un carattere U+FFFD che poi fa scattare lo stesso crash. Con una riga di correzione sarebbe pronta per la produzione.
