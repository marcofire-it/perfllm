#!/usr/bin/env python3
"""logstats.py - Analizzatore di log a riga di comando."""

import sys
import json
import re
import math
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict


VALID_LEVELS = frozenset(('DEBUG', 'INFO', 'WARN', 'ERROR'))

_TS_RE = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$'
)


def parse_timestamp(ts_str):
    """Parse un timestamp ISO-like e restituisce un datetime UTC, o None."""
    m = _TS_RE.match(ts_str)
    if not m:
        return None
    try:
        year, month, day = int(m[1]), int(m[2]), int(m[3])
        hour, minute, second = int(m[4]), int(m[5]), int(m[6])
        tz_str = m[7]
        if tz_str == 'Z':
            tz = timezone.utc
        else:
            sign = 1 if tz_str[0] == '+' else -1
            th, tm = int(tz_str[1:3]), int(tz_str[4:6])
            tz = timezone(timedelta(hours=sign * th, minutes=sign * tm))
        dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_line(line):
    """Parse una riga di log. Restituisce (ts_utc, level, service, message) o None."""
    parts = line.split(None, 3)
    if len(parts) < 4:
        return None
    ts_str, level, service, message = parts
    if level not in VALID_LEVELS:
        return None
    ts = parse_timestamp(ts_str)
    if ts is None:
        return None
    return ts, level, service, message


def message_template(message):
    """Rimuove i token chiave=valore e compatta gli spazi."""
    remaining = []
    for token in message.split():
        idx = token.find('=')
        if idx > 0:          # chiave non vuota → è un k=v, lo saltiamo
            continue
        remaining.append(token)
    return ' '.join(remaining)


def extract_latency(message):
    """Estrae latency_ms=<int>=0 dal messaggio, oppure None."""
    for token in message.split():
        if token.startswith('latency_ms='):
            val_str = token[11:]
            try:
                v = int(val_str)
                if v >= 0:
                    return v
            except ValueError:
                pass
    return None


def format_utc(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class CLIParser(argparse.ArgumentParser):
    """ArgumentParser che esce con codice 1 in caso di errore."""
    def error(self, message):
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = CLIParser(add_help=False)
    parser.add_argument('file')
    parser.add_argument('--since', default=None)
    parser.add_argument('--until', default=None)
    parser.add_argument('--level', default=None)
    parser.add_argument('--top', type=int, default=3)

    args = parser.parse_args()

    # --- validazione argomenti ---
    if args.top < 0:
        print("Error: --top must be >= 0", file=sys.stderr)
        sys.exit(1)

    if args.level is not None and args.level not in VALID_LEVELS:
        print(f"Error: invalid level '{args.level}'", file=sys.stderr)
        sys.exit(1)

    since_ts = None
    if args.since is not None:
        since_ts = parse_timestamp(args.since)
        if since_ts is None:
            print(f"Error: invalid --since timestamp '{args.since}'", file=sys.stderr)
            sys.exit(1)

    until_ts = None
    if args.until is not None:
        until_ts = parse_timestamp(args.until)
        if until_ts is None:
            print(f"Error: invalid --until timestamp '{args.until}'", file=sys.stderr)
            sys.exit(1)

    # --- lettura file ---
    try:
        f = open(args.file, 'r', encoding='utf-8')
    except (FileNotFoundError, PermissionError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    # --- elaborazione ---
    malformed = 0
    total = 0
    by_level = defaultdict(int)
    by_service_count = defaultdict(int)
    by_service_errors = defaultdict(int)
    latencies = []
    templates = defaultdict(int)
    ts_min = None
    ts_max = None

    with f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue

            parsed = parse_line(stripped)
            if parsed is None:
                malformed += 1
                continue

            ts, level, service, msg = parsed

            # filtri (le malformate sono già state contate sopra)
            if since_ts is not None and ts < since_ts:
                continue
            if until_ts is not None and ts > until_ts:
                continue
            if args.level is not None and level != args.level:
                continue

            total += 1
            by_level[level] += 1
            by_service_count[service] += 1
            if level == 'ERROR':
                by_service_errors[service] += 1

            if ts_min is None or ts < ts_min:
                ts_min = ts
            if ts_max is None or ts > ts_max:
                ts_max = ts

            lat = extract_latency(msg)
            if lat is not None:
                latencies.append(lat)

            tmpl = message_template(msg)
            templates[tmpl] += 1

    # --- latency_ms ---
    if latencies:
        latencies.sort()
        n = len(latencies)
        p95_idx = math.ceil(0.95 * n)          # 1-based, nearest-rank
        latency_stats = {
            'count': n,
            'min': latencies[0],
            'max': latencies[-1],
            'avg': round(sum(latencies) / n, 2),
            'p95': latencies[p95_idx - 1],
        }
    else:
        latency_stats = None

    # --- top_messages ---
    sorted_tmpl = sorted(templates.items(), key=lambda x: (-x[1], x[0]))
    top_messages = [{'message': m, 'count': c} for m, c in sorted_tmpl[:args.top]]

    # --- by_service (ordine alfabetico) ---
    by_service = {}
    for svc in sorted(by_service_count):
        by_service[svc] = {
            'count': by_service_count[svc],
            'errors': by_service_errors.get(svc, 0),
        }

    # --- risultato ---
    result = {
        'total': total,
        'malformed': malformed,
        'by_level': dict(sorted(by_level.items())),
        'by_service': by_service,
        'latency_ms': latency_stats,
        'top_messages': top_messages,
        'first_timestamp': format_utc(ts_min) if ts_min else None,
        'last_timestamp': format_utc(ts_max) if ts_max else None,
    }

    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
