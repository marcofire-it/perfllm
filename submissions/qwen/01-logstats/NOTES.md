# NOTES — task 01 `logstats`

## Scelte di design

- **Parsing CLI manuale** (niente `argparse`): il task richiede codice di uscita `1` per
  argomenti invalidi, mentre `argparse` userebbe `2` (riservato al file non leggibile).
  `-h`/`--help` stampa l'uso su stdout ed esce con `0`.
- **Timestamp**: validazione con regex (`YYYY-MM-DDTHH:MM:SS` + `Z` o `±HH:MM`) seguita da
  `datetime.fromisoformat`, che scarta anche date inesistenti (es. mese 13). Il timestamp
  senza fuso orario è considerato non parsabile → riga malformata. Tutti i confronti e
  l'output sono in UTC.
- **Token `chiave=valore`**: token delimitato da spazi con almeno un carattere `\w` prima
  di `=` e nessun carattere vuoto attorno (`(?<!\S)\w+=\S+(?!\S)`). La latenza è
  `latency_ms=<solo cifre>` come token intero: `latency_ms=120abc` o `latency_ms=-5`
  vengono ignorati (la riga resta valida).
- **p95 nearest-rank** calcolato con aritmetica intera esatta, `rank = (19n + 19) // 20`
  (poiché 0.95 = 19/20), per evitare errori di arrotondamento in float (es. `n = 20`).
- **Performance**: singolo passaggio O(n) sul file, regex pre-compilate, nessuna
  struttura quadratica. ~1.000.000 di righe elaborate in ~3,5 s (misurato su questa macchina).

## Assunzioni (punti ambigui della specifica)

- Riga con solo 3 campi (messaggio vuoto) → **malformata** ("manca uno dei 4 campi").
- Più token `latency_ms=` in una riga: viene considerato il **primo** valido.
- `avg` sempre stampato come float Python (es. `485.0`), `round(..., 2)`.
- File letto con `encoding="utf-8", errors="replace"`: byte non UTF-8 non fanno crashare
  lo script; la riga viene valutata normalmente (probabilmente malformata).
- `--since` > `--until` non è un errore: produce semplicemente un risultato vuoto.
- Opzioni duplicate: vale l'ultima occorrenza; più di un file posizionale → errore `1`.
- `--top 0` è valido e produce `top_messages: []`.

## Limiti noti

- Il file viene letto per righe: su file molto grandi la memoria resta O(distinta)
  (template/servizi/latency), non O(file).
- `p95`/`min`/`max` memorizzano tutte le latenze in lista (necessario per l'ordinamento);
  per 1M di righe sono ~tensine di MB.

## Come ho testato

- `test_logstats.py` (14 test `unittest`, eseguiti via subprocess contro lo script reale):
  entrambi gli esempi del task (output confrontato campo per campo), righe malformate di
  ogni tipo, filtri since/until/level (inclusività e conversione UTC da offset), `--top`,
  template vuoto, p95 nearest-rank, file vuoto, codici di uscita 0/1/2 e assenza di
  output su stdout in caso di errore. Tutti i test passano:
  `python -m unittest test_logstats`.
- Misurazione manuale su file generato di 1.000.000 di righe: ~3,5 s, risultato corretto.
