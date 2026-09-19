# NOTES — logstats.py

## Design

- **Parsing riga**: `line.strip()` per ignorare spazi iniziali/finali; righe vuote/blank
  vengono saltate (non contate). Split dei primi 3 campi con `re.split(r'\s+', line, maxsplit=3)`:
  questo consuma correttamente run di spazi multipli come separatori tra `timestamp`, `LEVEL`,
  `service`, ma lascia il `message` con la sua spaziatura interna originale (necessario per
  riprodurre l'esempio con `GET /  latency_ms=10`, doppio spazio prima del token).
- Riga malformata se: meno di 4 campi, timestamp non conforme al pattern
  `YYYY-MM-DDTHH:MM:SS(Z|±HH:MM)` o non parsabile, oppure `LEVEL` non in
  `{DEBUG, INFO, WARN, ERROR}`. Il conteggio `malformed` è sempre incrementato,
  indipendentemente dai filtri `--since/--until/--level`.
- **Timestamp**: validato con regex rigida (solo formato specificato, nessun supporto per
  frazioni di secondo), poi parsato con `datetime.fromisoformat` (sostituendo `Z` con
  `+00:00`) e convertito in UTC con `.astimezone(timezone.utc)`.
- **Filtri `--since/--until`**: confronto inclusivo in UTC sulle righe valide; le righe
  fuori range non contribuiscono a `total` né alle altre statistiche (ma contano comunque
  come "valide" ai fini del parsing — solo `malformed` resta indipendente).
- **Elaborazione single-pass**: nessuna struttura O(n²); si accumulano contatori/dizionari
  mentre si scorre il file una sola volta, così lo script scala linearmente
  (~3.8s su 1.000.000 di righe nel test locale).
- **Token chiave=valore**: un token (delimitato da whitespace) è considerato `chiave=valore`
  se contiene `=` con parte sinistra e destra entrambe non vuote (`k, _, v = tok.partition('=')`,
  `k != '' and v != ''`). Questi token vengono rimossi per calcolare il *template* del
  messaggio (join dei token restanti con un singolo spazio); un template vuoto è incluso
  come `"message": ""`.
- **`latency_ms`**: cercato tra i token `chiave=valore` del messaggio con chiave esattamente
  `latency_ms` e valore composto solo da cifre (`str.isdigit()`, quindi intero non negativo,
  niente segno/decimali). **Assunzione**: se nel messaggio compaiono più token `latency_ms=`
  validi, viene usato il **primo** incontrato scorrendo il messaggio da sinistra a destra;
  gli altri vengono comunque rimossi dal template come qualunque altro token chiave=valore.
  Un token `latency_ms=<non-intero>` (es. `abc`) viene ignorato ai fini della statistica ma
  la riga resta valida e il token viene comunque rimosso dal template.
- **p95**: metodo nearest-rank, `idx = ceil(0.95 * n)` (1-based) su lista ordinata crescente.
- **`top_messages`**: ordinato per `count` decrescente, poi `message` crescente
  (ordinamento lessicografico Python standard, case-sensitive su code point Unicode).
- **Argomenti CLI**: `argparse` con una sottoclasse che intercetta `error()` per garantire
  **exit code 1** (invece del default 2 di argparse) su argomenti non validi:
  `--top` negativo, `--level` non tra i 4 ammessi (validato con `choices`), `--since`/`--until`
  non parsabili. Il file non trovato/non leggibile produce invece **exit code 2**, con
  messaggio su stderr e nessun output su stdout in entrambi i casi di errore.
- **Lettura file**: apertura in `utf-8` con `errors="replace"` per evitare crash su file con
  byte non validi (non specificato dal task; scelta conservativa per robustezza).

## Limiti noti

- Se un messaggio contiene più token `latency_ms=<valore valido>`, viene usato solo il primo
  (assunzione documentata sopra; il task non specifica il comportamento in questo caso).
- Non vengono gestiti timestamp con frazioni di secondo (non richiesti dal formato specificato
  nel task).
- Il confronto lessicografico di `top_messages` è quello nativo di Python (case-sensitive,
  per code point), come da indicazione "ordine lessicografico semplice".

## Come ho testato

- Riprodotti manualmente ed esattamente sia l'esempio principale sia il "caso limite" del
  task (`TASK.md`), confrontando l'output con quello atteso: entrambi combaciano.
- Test automatici in `test_logstats.py` (solo `unittest`, nessuna dipendenza esterna),
  13 casi che coprono: esempio del task, caso limite del task, file non trovato (exit 2),
  argomenti non validi (`--top -1`, `--level FOO`, `--since` non parsabile → exit 1),
  righe vuote ignorate, filtro `--level`, filtro `--since/--until` inclusivo,
  ordinamento di `top_messages`, template vuoto, calcolo p95 nearest-rank.
  Eseguiti con `python -m unittest test_logstats.py -v` → tutti OK.
- Test di performance manuale: file generato con 1.000.000 di righe valide e casuali,
  eseguito con `--top 3`, tempo ~3.8s in locale (elaborazione single-pass, nessun algoritmo
  quadratico).
