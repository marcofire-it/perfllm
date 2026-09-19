# NOTES — logstats.py

## Scelte di design

- **Parsing timestamp**: regex per validare il formato `YYYY-MM-DDTHH:MM:SS(Z|±HH:MM)`, poi conversione a UTC tramite `datetime.astimezone()`. Errori di valori fuori range (es. mese 13) sono catturati da `datetime()` → riga malformata.
- **Token chiave=valore**: un token (delimitato da spazi) che contiene `=` con chiave non vuota (indice di `=` > 0). Il token `=valore` (chiave vuota) non è considerato k=v. Il token `chiave=` (valore vuoto) è considerato k=v e viene rimosso dal template.
- **Latenza negativa**: `latency_ms=-5` è ignorato (la specifica richiede "intero non negativo"); il token resta comunque un k=v e viene rimosso dal template del messaggio.
- **Efficienza**: singola passata O(n) sul file, con dizionari per i conteggi. L'ordinamento finale di latenze e template è O(k log k) dove k ≪ n tipicamente.
- **Lettura file**: iterazione riga per riga (non `readlines()`) per contenere l'uso di memoria su file grandi.
- **Codici di uscita**: `argparse.ArgumentParser.error()` sovrascritto per restituire exit code 1 (anziché 2 di default) per argomenti non validi; exit code 2 solo per errori di apertura file.

## Assunzioni

- L'encoding del file di log è UTF-8 (default ragionevole, non specificato nel task).
- Un token come `a=b=c` è considerato k=v (chiave `a`, valore `b=c`), poiché il primo `=` ha indice > 0.
- Se `--top 0`, `top_messages` è un array vuoto `[]`.

## Limiti noti

- Non gestisce timestamp con frazioni di secondo (es. `T12:34:56.789Z`), poiché non previsti dal formato specificato.
- Non supporta encoding diversi da UTF-8.

## Test

20 test in `test_logstats.py` coprono:
- Esempi del task (principale e caso limite)
- Filtri `--since`, `--until`, `--level`, `--top 0`
- Codici di uscita (file non trovato, livello invalido, top negativo, timestamp invalido)
- File vuoto, solo righe bianche, tutte malformate
- Template vuoto (messaggio fatto solo di k=v)
- Offset negativi nel timestamp
- Calcolo p95 con 1 e 20 valori
- Ordinamento top_messages (count desc, message asc)
- Rimozione multipla di k=v e compattamento spazi
