# Task 01 — `logstats`: command-line log analyzer

**Level: 1 (easy)** · Files to deliver: `logstats.py`, `NOTES.md`

## Goal

Write a script `logstats.py` (single file, standard library only) that reads a text log file
and prints a JSON summary to stdout.

## Log format

Each line has the form:

```
<timestamp> <LEVEL> <service> <message>
```

separated by **one or more spaces**. Example:

```
2024-03-01T12:34:56Z INFO auth Login ok user=42 latency_ms=120
2024-03-01T12:35:01+02:00 ERROR payments Charge failed order=9 latency_ms=850
2024-03-01T12:35:02Z WARN auth Token near expiry user=42
```

- `timestamp`: `YYYY-MM-DDTHH:MM:SS` followed by `Z` or by an offset `+HH:MM` / `-HH:MM`.
- `LEVEL`: one of `DEBUG`, `INFO`, `WARN`, `ERROR` (uppercase).
- `service`: token without spaces.
- `message`: the whole rest of the line (may contain spaces). The message may contain
  `key=value` tokens (no spaces around `=`).

A line is **malformed** if: one of the 4 fields is missing, the timestamp cannot be parsed, the level is
not among the allowed ones. Malformed lines are **counted** but excluded from all statistics.
Empty lines or lines made only of whitespace are **ignored** (counted neither as malformed nor as total).
Leading/trailing whitespace of a line must be ignored.

## CLI interface

```
python logstats.py <file> [--since <ts>] [--until <ts>] [--level <LEVEL>] [--top <N>]
```

- `--since` / `--until`: timestamp in the same format as the logs; the filter is **inclusive** at both ends,
  comparison done in UTC. Lines outside the range are excluded from the statistics and **not** counted in `total`.
- `--level`: consider only lines with that level (same treatment as above).
- `--top N`: maximum number of entries in `top_messages` (default 3). `N` must be an integer ≥ 0.
- The `malformed` count is **independent of the filters** (a malformed line is always counted).

Exit codes:
- `0` success;
- `2` file not found or not readable (message on stderr);
- `1` invalid arguments (e.g. `--top -1`, `--level FOO`, unparsable `--since` timestamp), message on stderr.

On error nothing must be printed to stdout.

## Output (JSON on stdout, a single object)

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

Rules:

- `total`: valid lines that pass the filters.
- `by_level`: only levels with count > 0, keys in alphabetical order.
- `by_service`: keys in alphabetical order; `errors` = lines with level `ERROR` for that service.
- `latency_ms`: computed over the (valid and filtered) lines whose message contains a token
  `latency_ms=<non-negative integer>`. If the value is not a valid integer the token is ignored
  (the line stays valid). `avg` rounded to 2 decimals (float), `min`/`max`/`p95` integers.
  `p95` with the **nearest-rank** method: sort the values in ascending order, take the element at
  position `ceil(0.95 * n)` (1-based). If there are no values: `"latency_ms": null`.
- `top_messages`: group by **message template**, i.e. the message after removing all
  `key=value` tokens and collapsing runs of whitespace into a single space (trimmed at both ends).
  Sort by `count` descending, then by `message` ascending (plain lexicographic order).
  Take the first `N` entries. An empty template (message made only of key=value tokens) must still be
  included with `"message": ""`.
- `first_timestamp` / `last_timestamp`: min and max of the timestamps of the considered lines, in UTC, format
  `YYYY-MM-DDTHH:MM:SSZ`. If `total` is 0: both `null`.
- The order of lines in the file is **not** guaranteed to be chronological.
- The JSON must be valid; indentation is free. The keys must be exactly those listed.

## Edge-case example

File:
```
2024-01-01T00:00:00Z INFO web GET /  latency_ms=10

this line is broken
2024-01-01T00:00:00Z FATAL web boom
2023-12-31T23:00:00-02:00 ERROR web GET /  latency_ms=abc
```
Expected output (formatting aside):
```json
{"total": 2, "malformed": 2,
 "by_level": {"ERROR": 1, "INFO": 1},
 "by_service": {"web": {"count": 2, "errors": 1}},
 "latency_ms": {"count": 1, "min": 10, "max": 10, "avg": 10.0, "p95": 10},
 "top_messages": [{"message": "GET /", "count": 2}],
 "first_timestamp": "2024-01-01T00:00:00Z", "last_timestamp": "2024-01-01T01:00:00Z"}
```

## Constraints

- A single file `logstats.py`, runnable with `python logstats.py ...`.
- Must handle files of ~1 million lines in reasonable time (no quadratic algorithms).
- No external dependencies.
