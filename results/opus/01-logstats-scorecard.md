# Scorecard — modello: `opus` · task: `01-logstats` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `34/34` → core `17/17`, edge `16/16`, perf `1/1`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`logstats.py`, opzioni `--since/--until/--level/--top`, chiavi JSON esatte, exit code 0/1/2)
- Dipendenze esterne / costrutti vietati: nessuna (solo stdlib)
- Formato consegna (file integrali, NOTES.md): ok (logstats.py, NOTES.md, test_logstats.py, tutti integrali)
- Deviazioni non documentate: nessuna. Documentate: `a=` (valore vuoto) considerato k=v e rimosso, `=x` no; solo UTF-8; `--help` disattivato (`add_help=False`, riga 92) e quindi `--help` esce con 1 come argomento sconosciuto (non specificato dalla spec)
- **B = 15/15**

## C. Qualità del codice (15)
- Struttura: helper piccoli e chiari (`parse_timestamp`, `parse_line`, `message_template`, `extract_latency`), ma `main()` (righe 91-221) è un monolite di 130 righe che fa parsing argomenti, validazione, apertura file, accumulo statistiche e serializzazione. Non esiste una funzione `process(...)` testabile senza subprocess.
- Gestione errori / risorse: `open` gestito con exit 2, ma l'`OSError` durante l'iterazione (riga 143) non è catturato. Lettura in `utf-8` strict (riga 126): un byte non UTF-8 produce `UnicodeDecodeError` con traceback. `json.dump(..., ensure_ascii=False)` su `sys.stdout` (riga 220) senza gestione dell'encoding della console: su Windows con stdout cp1252 un messaggio con caratteri non latini fa esplodere la serializzazione a metà, lasciando JSON troncato su stdout.
- Punti di forza: regex timestamp rigorosa con conversione offset esplicita, singolo passaggio O(n), sottoclasse `argparse` per l'exit code 1, `defaultdict` puliti.
- Punti deboli: monolite in `main`, nessuna difesa sull'encoding in ingresso e in uscita, docstring con refuso (`latency_ms=<int>=0`, riga 67).
- **C = 10/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| File con BOM UTF-8 | prima riga malformata o valida | prima riga malformata (total 1, malformed 1) | ok |
| Messaggio unicode (`Ciao è mondo 日本`) + 20 token k=v, console cp1252 | JSON con template `Ciao è mondo 日本` | `UnicodeEncodeError`, traceback, exit 1, **JSON troncato su stdout** | ko |
| `--since` dopo `--until` | total 0, null, exit 0 | total 0, latency null, ts null, exit 0 | ok |
| File vuoto | total 0, malformed 0, exit 0 | corretto | ok |
| `--top 100000` | 1 voce | 1 voce, count 5 | ok |
| Timestamp con secondi frazionari | riga malformata | malformed 1, total 1 | ok |
| `latency_ms=99999999999999999999` | int esatti, avg float | min/max/p95 esatti, avg `1e+20` | ok |
| 5 righe identiche | total 5, first==last | corretto | ok |
| Righe CRLF | total 2, template `GET /` | corretto | ok |
| Byte non UTF-8 (`caf\xe9`) | nessun crash | `UnicodeDecodeError`, traceback, exit 1 | ko |
| `--top abc` | exit 1, stdout vuoto | exit 1, stdout vuoto | ok |
| `--foo` | exit 1 | exit 1 | ok |
| Directory al posto del file | exit 2 | exit 2 | ok |
| `request-id=abc =x y= a=b=c` | k=v rimossi | template `GET =x done` (rimuove anche `y=` e `request-id=abc`) | ok |
- Due crash con traceback su input plausibili (unicode su console Windows, file non UTF-8); nel primo caso viola anche "nulla su stdout in caso di errore".
- **D = 3/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, sintetico e onesto: scelte, assunzioni (`a=b=c`, `a=`, `--top 0`), limiti reali (frazioni di secondo, solo UTF-8)
- Assunzioni dichiarate coerenti con il codice: sì (verificate `idx > 0`, latenza negativa ignorata ma token rimosso)
- Test propri: buoni (20 test `unittest` via subprocess, passano tutti; coprono errori, exit code, file vuoto, p95 con 1 e 20 valori, ordinamento, template vuoto)
- **E = 5/5**

## Totale: **88 / 100**

## Commento
Implementazione corretta al 100% sui test nascosti: ha gestito tutte le trappole di TRAPS.md (malformed indipendente dai filtri, p95 nearest-rank, offset timezone, `FATAL` malformato, `--top abc` con exit 1 grazie alla sottoclasse di argparse, template vuoto incluso). La logica è pulita e le assunzioni sono documentate. Perde punti dove la spec non arrivava: nessuna difesa sull'encoding, né in lettura (`utf-8` strict) né in scrittura (`ensure_ascii=False` senza curarsi della console), quindi su Windows un log con caratteri non latini fa crashare lo script lasciando JSON troncato su stdout. Il `main` monolitico rende il codice meno testabile dei concorrenti. Usabile in produzione dopo due correzioni piccole (`errors="replace"` e `ensure_ascii=True` o riconfigurazione di stdout).
