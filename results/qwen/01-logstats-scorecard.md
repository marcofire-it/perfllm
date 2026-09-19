# Scorecard — modello: `qwen` · task: `01-logstats` · data: 2026-09-19

## A. Test automatici (55)
- Test superati: `34/34` → core `17/17`, edge `16/16`, perf `1/1`
- Test falliti principali e causa: nessuno
- **A = 55/55**

## B. Aderenza a spec e istruzioni (15)
- Nomi/interfacce rispettati: sì (`logstats.py`, opzioni esatte, chiavi JSON esatte, exit code 0/1/2; in più `-h/--help` con exit 0)
- Dipendenze esterne / costrutti vietati: nessuna (solo stdlib)
- Formato consegna (file integrali, NOTES.md): ok (logstats.py, NOTES.md, test_logstats.py, più `sample.log` di supporto)
- Deviazioni non documentate: nessuna. Deviazione documentata ma discutibile: un token è k=v solo se la chiave è `\w+` (regex riga 38), quindi `request-id=abc` **non** viene rimosso dal template. La spec dice solo "token chiave=valore senza spazi attorno a =" e chiavi con trattino sono comuni nei log: −1 come deviazione minore.
- **B = 14/15**

## C. Qualità del codice (15)
- Struttura: chiara e ben separata (`parse_args`, `parse_line`, `message_template`, `analyze`, `main(argv)`), costanti e regex pre-compilate in testa, docstring su ogni funzione. Parser CLI scritto a mano (righe 100-144) con motivazione esplicita in NOTES (exit code 1 invece del 2 di argparse): gestisce opzioni senza valore, opzioni sconosciute, file duplicato, `--help`.
- Gestione errori / risorse: `fail()` centralizza stderr + exit (riga 46); apertura file con `errors="replace"` e `OSError` → exit 2; output con `ensure_ascii` di default, quindi nessun problema di encoding della console. `fail()` chiamata dentro `analyze()` (riga 161) mescola logica e terminazione del processo: la funzione non è riusabile come libreria. L'`OSError` durante l'iterazione non è catturato.
- Punti di forza: p95 con aritmetica intera esatta `(19n+19)//20` (riga 206), sentinella `_MALFORMED` per distinguere i tre esiti del parser, nessuna dipendenza dall'encoding della console.
- Punti deboli: `sys.exit` annidato nella logica di analisi; regex k=v troppo restrittiva sulla chiave; il parser manuale è più codice da mantenere di argparse.
- **C = 13/15**

## D. Robustezza oltre i test (10)
| Input provato | Atteso | Ottenuto | Esito |
|---|---|---|---|
| File con BOM UTF-8 | prima riga malformata o valida | prima riga malformata (total 1, malformed 1) | ok |
| Messaggio unicode (`Ciao è mondo 日本`) + 20 token k=v, console cp1252 | JSON con template `Ciao è mondo 日本` | corretto (escape `\uXXXX`), latency 5 | ok |
| `--since` dopo `--until` | total 0, null, exit 0 | corretto | ok |
| File vuoto | total 0, malformed 0, exit 0 | corretto | ok |
| `--top 100000` | 1 voce | 1 voce, count 5 | ok |
| Timestamp con secondi frazionari | riga malformata | malformed 1, total 1 | ok |
| `latency_ms=99999999999999999999` | int esatti, avg float | min/max/p95 esatti, avg `1e+20` | ok |
| 5 righe identiche | total 5, first==last | corretto | ok |
| Righe CRLF | total 2, template `GET /` | corretto | ok |
| Byte non UTF-8 (`caf\xe9`) | nessun crash | total 1, template `caf�`, exit 0 | ok |
| `--top abc` | exit 1, stdout vuoto | exit 1, messaggio chiaro | ok |
| `--foo` | exit 1 | exit 1 con usage | ok |
| Directory al posto del file | exit 2 | exit 2 | ok |
| `request-id=abc =x y= a=b=c` | k=v rimossi | template `GET request-id=abc =x y= done`: chiave con trattino non riconosciuta (già penalizzato in B) | ko (minore) |
- Nessun crash; unico comportamento discutibile è la definizione stretta di k=v.
- **D = 10/10**

## E. NOTES.md e test propri (5)
- NOTES.md: presente, ben organizzato: motivazione del parser manuale, definizione di k=v, p95 intero, sezione "Assunzioni (punti ambigui)" con 7 voci concrete, limiti di memoria reali
- Assunzioni dichiarate coerenti con il codice: sì (verificate regex k=v, primo `latency_ms`, opzioni duplicate, `--since > --until`)
- Test propri: buoni (14 test `unittest` via subprocess, passano tutti; malformate di ogni tipo, filtri UTC, `--top`, template vuoto, p95, exit code e stdout vuoto in errore)
- **E = 5/5**

## Totale: **97 / 100**

## Commento
Consegna corretta al 100% e la più robusta delle tre: è l'unica che non crasha su unicode con console Windows né su byte non UTF-8, perché ha lasciato `ensure_ascii` di default e letto con `errors="replace"`. Ha gestito tutte le trappole di TRAPS.md e ha scelto consapevolmente di scrivere il parser CLI a mano proprio per rispettare l'exit code 1 (la spec riserva il 2 al file): scelta più laboriosa ma motivata e ben eseguita, con `--help` e opzioni sconosciute gestite. Il punto debole è la definizione di token k=v limitata a chiavi `\w+`: `request-id=abc` resta nel template, un caso realistico nei log. Documentato, ma è un'interpretazione più stretta del necessario. Codice pronto per la produzione così com'è.
