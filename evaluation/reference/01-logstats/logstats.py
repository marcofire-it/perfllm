#!/usr/bin/env python3
"""Implementazione di riferimento per il task 01 (logstats)."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
KV_RE = re.compile(r"\S+=\S+")
LAT_RE = re.compile(r"(?:^|\s)latency_ms=(\S+)")


def parse_ts(text: str) -> datetime | None:
    if not TS_RE.match(text):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def template(message: str) -> str:
    return " ".join(tok for tok in message.split() if not KV_RE.fullmatch(tok))


def latency_of(message: str) -> int | None:
    for tok in message.split():
        if tok.startswith("latency_ms="):
            val = tok[len("latency_ms="):]
            if val.isdigit():
                return int(val)
            return None
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="logstats", add_help=True)
    ap.add_argument("file")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--level")
    ap.add_argument("--top", type=int, default=3)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        # argparse esce con 2 per argomenti errati e 0 per --help; normalizziamo a 1 gli errori
        return 1 if e.code not in (0, None) else 0

    since = until = None
    if args.since is not None:
        since = parse_ts(args.since)
        if since is None:
            print("errore: --since non valido", file=sys.stderr)
            return 1
    if args.until is not None:
        until = parse_ts(args.until)
        if until is None:
            print("errore: --until non valido", file=sys.stderr)
            return 1
    if args.level is not None and args.level not in LEVELS:
        print("errore: --level non valido", file=sys.stderr)
        return 1
    if args.top < 0:
        print("errore: --top deve essere >= 0", file=sys.stderr)
        return 1

    try:
        fh = open(args.file, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"errore: impossibile leggere {args.file}: {e}", file=sys.stderr)
        return 2

    total = 0
    malformed = 0
    by_level: Counter[str] = Counter()
    by_service: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "errors": 0})
    latencies: list[int] = []
    templates: Counter[str] = Counter()
    first_ts = last_ts = None

    with fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            parts = line.split(None, 3)
            if len(parts) < 4:
                malformed += 1
                continue
            ts_s, level, service, message = parts
            ts = parse_ts(ts_s)
            if ts is None or level not in LEVELS:
                malformed += 1
                continue
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue
            if args.level is not None and level != args.level:
                continue

            total += 1
            by_level[level] += 1
            svc = by_service[service]
            svc["count"] += 1
            if level == "ERROR":
                svc["errors"] += 1
            lat = latency_of(message)
            if lat is not None:
                latencies.append(lat)
            templates[template(message)] += 1
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

    if latencies:
        latencies.sort()
        n = len(latencies)
        lat_stats = {
            "count": n,
            "min": latencies[0],
            "max": latencies[-1],
            "avg": round(sum(latencies) / n, 2),
            "p95": latencies[max(math.ceil(0.95 * n), 1) - 1],
        }
    else:
        lat_stats = None

    top = sorted(templates.items(), key=lambda kv: (-kv[1], kv[0]))[: args.top]

    out = {
        "total": total,
        "malformed": malformed,
        "by_level": {k: by_level[k] for k in sorted(by_level)},
        "by_service": {k: by_service[k] for k in sorted(by_service)},
        "latency_ms": lat_stats,
        "top_messages": [{"message": m, "count": c} for m, c in top],
        "first_timestamp": fmt_ts(first_ts) if first_ts else None,
        "last_timestamp": fmt_ts(last_ts) if last_ts else None,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
