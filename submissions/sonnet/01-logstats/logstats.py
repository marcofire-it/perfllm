#!/usr/bin/env python3
"""logstats.py -- analizzatore di log a riga di comando.

Legge un file di log testuale e stampa su stdout un riepilogo in JSON.
Sola libreria standard, nessuna dipendenza esterna.
"""

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone

ALLOWED_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

# Timestamp: YYYY-MM-DDTHH:MM:SS seguito da Z oppure da offset +HH:MM/-HH:MM
TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)

FIELD_SPLIT_RE = re.compile(r"\s+")


def parse_timestamp(ts_str):
    """Ritorna un datetime timezone-aware in UTC, oppure None se non valido."""
    if not TS_RE.match(ts_str):
        return None
    normalized = ts_str[:-1] + "+00:00" if ts_str.endswith("Z") else ts_str
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


def format_timestamp(dt_utc):
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_kv_token(token):
    """True se il token e' nella forma chiave=valore (entrambe non vuote)."""
    if "=" not in token:
        return False
    key, _, val = token.partition("=")
    return key != "" and val != ""


def build_parser():
    class ArgParser(argparse.ArgumentParser):
        def error(self, message):
            print(f"logstats: errore argomenti: {message}", file=sys.stderr)
            sys.exit(1)

    parser = ArgParser(
        prog="logstats.py",
        description="Analizza un file di log e stampa un riepilogo JSON.",
    )
    parser.add_argument("file", help="percorso del file di log")
    parser.add_argument("--since", default=None, help="timestamp minimo (incluso)")
    parser.add_argument("--until", default=None, help="timestamp massimo (incluso)")
    parser.add_argument(
        "--level", default=None, choices=list(ALLOWED_LEVELS), help="filtra per livello"
    )
    parser.add_argument("--top", type=int, default=3, help="numero massimo di top_messages")
    return parser


def parse_line(raw_line):
    """Effettua il parsing di una riga.

    Ritorna None se la riga va ignorata (vuota/whitespace).
    Ritorna ('malformed', None) se la riga e' malformata.
    Ritorna ('ok', (ts_utc, level, service, message)) se valida.
    """
    line = raw_line.strip()
    if line == "":
        return None

    parts = FIELD_SPLIT_RE.split(line, maxsplit=3)
    if len(parts) < 4:
        return ("malformed", None)

    ts_str, level, service, message = parts

    ts_utc = parse_timestamp(ts_str)
    if ts_utc is None:
        return ("malformed", None)

    if level not in ALLOWED_LEVELS:
        return ("malformed", None)

    if service == "":
        return ("malformed", None)

    return ("ok", (ts_utc, level, service, message))


def process(fileobj, since, until, level_filter, top_n):
    total = 0
    malformed = 0
    by_level = {}
    by_service = {}
    latencies = []
    template_counts = {}
    first_ts = None
    last_ts = None

    for raw_line in fileobj:
        result = parse_line(raw_line)
        if result is None:
            continue
        kind = result[0]
        if kind == "malformed":
            malformed += 1
            continue

        ts_utc, level, service, message = result[1]

        if since is not None and ts_utc < since:
            continue
        if until is not None and ts_utc > until:
            continue
        if level_filter is not None and level != level_filter:
            continue

        total += 1
        by_level[level] = by_level.get(level, 0) + 1

        svc = by_service.setdefault(service, {"count": 0, "errors": 0})
        svc["count"] += 1
        if level == "ERROR":
            svc["errors"] += 1

        if first_ts is None or ts_utc < first_ts:
            first_ts = ts_utc
        if last_ts is None or ts_utc > last_ts:
            last_ts = ts_utc

        tokens = message.split()
        template_tokens = []
        latency_value = None
        for tok in tokens:
            if is_kv_token(tok):
                if latency_value is None:
                    key, _, val = tok.partition("=")
                    if key == "latency_ms" and val.isdigit():
                        latency_value = int(val)
                continue
            template_tokens.append(tok)

        template = " ".join(template_tokens)
        template_counts[template] = template_counts.get(template, 0) + 1

        if latency_value is not None:
            latencies.append(latency_value)

    # by_level: solo livelli con count > 0, ordine alfabetico
    by_level_sorted = {k: by_level[k] for k in sorted(by_level.keys())}

    # by_service: ordine alfabetico delle chiavi
    by_service_sorted = {k: by_service[k] for k in sorted(by_service.keys())}

    # latency_ms
    if latencies:
        latencies.sort()
        n = len(latencies)
        idx = math.ceil(0.95 * n)
        if idx < 1:
            idx = 1
        p95 = latencies[idx - 1]
        latency_stats = {
            "count": n,
            "min": latencies[0],
            "max": latencies[-1],
            "avg": round(sum(latencies) / n, 2),
            "p95": p95,
        }
    else:
        latency_stats = None

    # top_messages
    top_list = sorted(template_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top_messages = [
        {"message": msg, "count": cnt} for msg, cnt in top_list[:top_n]
    ]

    result = {
        "total": total,
        "malformed": malformed,
        "by_level": by_level_sorted,
        "by_service": by_service_sorted,
        "latency_ms": latency_stats,
        "top_messages": top_messages,
        "first_timestamp": format_timestamp(first_ts) if total > 0 else None,
        "last_timestamp": format_timestamp(last_ts) if total > 0 else None,
    }
    return result


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.top < 0:
        parser.error("--top deve essere un intero >= 0")

    since = None
    if args.since is not None:
        since = parse_timestamp(args.since)
        if since is None:
            parser.error(f"--since non e' un timestamp valido: {args.since!r}")

    until = None
    if args.until is not None:
        until = parse_timestamp(args.until)
        if until is None:
            parser.error(f"--until non e' un timestamp valido: {args.until!r}")

    try:
        fileobj = open(args.file, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"logstats: impossibile leggere il file '{args.file}': {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        with fileobj:
            result = process(fileobj, since, until, args.level, args.top)
    except OSError as exc:
        print(f"logstats: errore durante la lettura del file: {exc}", file=sys.stderr)
        sys.exit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
