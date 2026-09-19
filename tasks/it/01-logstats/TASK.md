# Task 01 — `logstats`: analizzatore di log a riga di comando

**Livello: 1 (facile)** · File da consegnare: `logstats.py`, `NOTES.md`

## Obiettivo

Scrivere uno script `logstats.py` (file singolo, sola libreria standard) che legge un file di log
testuale e stampa su stdout un riepilogo in JSON.

## Formato del log

Ogni riga ha la forma:

```
<timestamp> <LEVEL> <service> <message>
```

separati da **uno o più spazi**. Esempio:

```
2024-03-01T12:34:56Z INFO auth Login ok user=42 latency_ms=120
2024-03-01T12:35:01+02:00 ERROR payments Charge failed order=9 latency_ms=850
2024-03-01T12:35:02Z WARN auth Token near expiry user=42
```

- `timestamp`: `YYYY-MM-DDTHH:MM:SS` seguito da `Z` oppure da un offset `+HH:MM` / `-HH:MM`.
- `LEVEL`: uno tra `DEBUG`, `INFO`, `WARN`, `ERROR` (maiuscolo).
- `service`: token senza spazi.
- `message`: tutto il resto della riga (può contenere spazi). Dentro il messaggio possono comparire
  token `chiave=valore` (senza spazi attorno a `=`).

Una riga è **malformata** se: manca uno dei 4 campi, il timestamp non è parsabile, il livello non è
tra quelli ammessi. Le righe malformate vengono **contate** ma escluse da tutte le statistiche.
Le righe vuote o composte solo da spazi vengono **ignorate** (non contate come malformate né come totali).
Gli spazi iniziali/finali della riga vanno ignorati.

## Interfaccia CLI

```
python logstats.py <file> [--since <ts>] [--until <ts>] [--level <LEVEL>] [--top <N>]
```

- `--since` / `--until`: timestamp nello stesso formato dei log; filtro **inclusivo** agli estremi,
  confronto fatto in UTC. Le righe fuori intervallo sono escluse dalle statistiche e **non** contate in `total`.
- `--level`: considera solo le righe con quel livello (stesso trattamento di sopra).
- `--top N`: numero massimo di voci in `top_messages` (default 3). `N` deve essere un intero ≥ 0.
- Il conteggio `malformed` è **indipendente dai filtri** (una riga malformata è sempre contata).

Codici di uscita:
- `0` successo;
- `2` file non trovato o non leggibile (messaggio su stderr);
- `1` argomenti non validi (es. `--top -1`, `--level FOO`, timestamp di `--since` non parsabile), messaggio su stderr.

In caso di errore non va stampato nulla su stdout.

## Output (JSON su stdout, un solo oggetto)

```json
{
  "total": 3,
  "malformed": 0,
  "by_level": {"ERROR": 1, "INFO": 1, "WARN": 1},
  "by_service": {
    "auth": {"count": 2, "errors": 0},
    "payments": {"count": 1, "errors": 1}
  },
  "latency_ms": {"count": 2, "min": 120, "max": 850, "avg": 485.0, "p95": 850},
  "top_messages": [
    {"message": "Charge failed", "count": 1},
    {"message": "Login ok", "count": 1},
    {"message": "Token near expiry", "count": 1}
  ],
  "first_timestamp": "2024-03-01T10:35:01Z",
  "last_timestamp": "2024-03-01T12:35:02Z"
}
```

Regole:

- `total`: righe valide che superano i filtri.
- `by_level`: solo i livelli con conteggio > 0, chiavi in ordine alfabetico.
- `by_service`: chiavi in ordine alfabetico; `errors` = righe con livello `ERROR` di quel servizio.
- `latency_ms`: calcolato sulle righe (valide e filtrate) il cui messaggio contiene un token
  `latency_ms=<intero non negativo>`. Se il valore non è un intero valido il token viene ignorato
  (la riga resta valida). `avg` arrotondato a 2 decimali (float), `min`/`max`/`p95` interi.
  `p95` con il metodo **nearest-rank**: ordinati i valori in modo crescente, prendi l'elemento in
  posizione `ceil(0.95 * n)` (1-based). Se non ci sono valori: `"latency_ms": null`.
- `top_messages`: raggruppa per **template del messaggio**, cioè il messaggio dopo aver rimosso tutti
  i token `chiave=valore` e compattato gli spazi multipli in uno (trim agli estremi).
  Ordina per `count` decrescente, poi per `message` crescente (ordine lessicografico semplice).
  Prendi le prime `N` voci. Un template vuoto (messaggio fatto solo di token chiave=valore) va comunque
  incluso con `"message": ""`.
- `first_timestamp` / `last_timestamp`: min e max dei timestamp delle righe considerate, in UTC, formato
  `YYYY-MM-DDTHH:MM:SSZ`. Se `total` è 0: `null` entrambi.
- L'ordine delle righe nel file **non** è garantito cronologico.
- Il JSON deve essere valido; l'indentazione è libera. Le chiavi devono essere esattamente quelle indicate.

## Esempio di caso limite

File:
```
2024-01-01T00:00:00Z INFO web GET /  latency_ms=10

questa riga è rotta
2024-01-01T00:00:00Z FATAL web boom
2023-12-31T23:00:00-02:00 ERROR web GET /  latency_ms=abc
```
Output atteso (formattazione a parte):
```json
{"total": 2, "malformed": 2,
 "by_level": {"ERROR": 1, "INFO": 1},
 "by_service": {"web": {"count": 2, "errors": 1}},
 "latency_ms": {"count": 1, "min": 10, "max": 10, "avg": 10.0, "p95": 10},
 "top_messages": [{"message": "GET /", "count": 2}],
 "first_timestamp": "2024-01-01T00:00:00Z", "last_timestamp": "2024-01-01T01:00:00Z"}
```

## Vincoli

- Un solo file `logstats.py`, eseguibile con `python logstats.py ...`.
- Deve gestire file di ~1 milione di righe in tempi ragionevoli (niente algoritmi quadratici).
- Nessuna dipendenza esterna.
