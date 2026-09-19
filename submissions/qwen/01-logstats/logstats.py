#!/usr/bin/env python3
"""logstats.py — command-line log analyzer (Python 3.11+, standard library only).

Reads a text log file whose lines have the form:

    <timestamp> <LEVEL> <service> <message>

(fields separated by one or more spaces) and prints a JSON summary on stdout.

Usage:
    python logstats.py <file> [--since <ts>] [--until <ts>] [--level <LEVEL>] [--top <N>]

Exit codes:
    0  success
    1  invalid arguments (bad --top, --level, --since/--until, unknown option, ...)
    2  log file not found or not readable
"""

import json
import re
import sys
from datetime import datetime, timezone

PROG = "logstats"

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

USAGE = (
    "usage: python logstats.py <file> [--since <ts>] [--until <ts>] "
    "[--level <LEVEL>] [--top <N>]"
)

# Timestamp: YYYY-MM-DDTHH:MM:SS followed by 'Z' or by an offset +HH:MM / -HH:MM.
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")

# A key=value token: a whitespace-delimited token containing '=' with at least
# one word character before it and no spaces around '='.
KV_TOKEN_RE = re.compile(r"(?<!\S)\w+=\S+(?!\S)")

# A valid latency token: latency_ms=<non-negative integer> as a whole token.
LATENCY_RE = re.compile(r"(?<!\S)latency_ms=(\d+)(?!\S)")

_MALFORMED = "malformed"


def fail(code, message):
    """Print an error on stderr and exit with the given code (nothing on stdout)."""
    print(f"{PROG}: {message}", file=sys.stderr)
    sys.exit(code)


def parse_timestamp(text):
    """Parse a timestamp in the log format; return an aware UTC datetime or None."""
    if not TS_RE.match(text):
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def parse_line(raw):
    """Parse one raw log line.

    Returns:
        None            -> blank / whitespace-only line (ignored)
        _MALFORMED      -> malformed line
        dict            -> {"ts", "level", "service", "message"}
    """
    line = raw.strip()
    if not line:
        return None
    parts = line.split(None, 3)
    if len(parts) < 4:
        return _MALFORMED  # missing one of the 4 fields
    ts = parse_timestamp(parts[0])
    if ts is None:
        return _MALFORMED
    level = parts[1]
    if level not in LEVELS:
        return _MALFORMED
    return {"ts": ts, "level": level, "service": parts[2], "message": parts[3]}


def message_template(message):
    """Message with all key=value tokens removed and whitespace collapsed."""
    return " ".join(KV_TOKEN_RE.sub(" ", message).split())


def fmt_ts(dt):
    """Format an aware datetime as UTC 'YYYY-MM-DDTHH:MM:SSZ' (None passes through)."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv):
    """Manually parse CLI arguments; exits with code 1 on any invalid argument."""
    file_path = None
    opts = {"since": None, "until": None, "level": None, "top": 3}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--since", "--until", "--level", "--top"):
            if i + 1 >= len(argv):
                fail(1, f"option {arg} requires a value\n{USAGE}")
            value = argv[i + 1]
            i += 2  # option + its value; `continue` skips the trailing i += 1
            key = arg[2:]
            if key == "top":
                try:
                    top = int(value)
                except ValueError:
                    fail(1, f"invalid --top value: {value!r} (expected an integer >= 0)")
                if top < 0:
                    fail(1, f"invalid --top value: {value!r} (expected an integer >= 0)")
                opts["top"] = top
            elif key == "level":
                if value not in LEVELS:
                    fail(1, f"invalid --level value: {value!r} "
                           f"(expected one of: {', '.join(LEVELS)})")
                opts["level"] = value
            else:  # --since / --until
                ts = parse_timestamp(value)
                if ts is None:
                    fail(1, f"invalid --{key} timestamp: {value!r}")
                opts[key] = ts
            continue
        elif arg in ("-h", "--help"):
            print(USAGE)
            sys.exit(0)
        elif arg.startswith("-") and len(arg) > 1:
            fail(1, f"unknown option: {arg}\n{USAGE}")
        else:
            if file_path is not None:
                fail(1, f"unexpected extra argument: {arg}\n{USAGE}")
            file_path = arg
        i += 1
    if file_path is None:
        fail(1, "missing log file\n" + USAGE)
    return file_path, opts


def analyze(path, since, until, level, top):
    """Stream the log file once (O(n)) and build the summary dictionary."""
    total = 0
    malformed = 0
    by_level = {}
    by_service = {}
    latencies = []
    templates = {}
    first = None
    last = None

    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        fail(2, f"cannot read file '{path}': {exc.strerror or exc}")

    with fh:
        for raw in fh:
            record = parse_line(raw)
            if record is None:
                continue
            if record is _MALFORMED:
                malformed += 1
                continue

            ts = record["ts"]
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue
            lvl = record["level"]
            if level is not None and lvl != level:
                continue

            total += 1
            by_level[lvl] = by_level.get(lvl, 0) + 1

            svc = by_service.setdefault(record["service"], {"count": 0, "errors": 0})
            svc["count"] += 1
            if lvl == "ERROR":
                svc["errors"] += 1

            m = LATENCY_RE.search(record["message"])
            if m is not None:
                latencies.append(int(m.group(1)))

            template = message_template(record["message"])
            templates[template] = templates.get(template, 0) + 1

            if first is None or ts < first:
                first = ts
            if last is None or ts > last:
                last = ts

    if latencies:
        vals = sorted(latencies)
        n = len(vals)
        # nearest-rank p95: ceil(0.95 * n), computed with exact integer math
        # (0.95 == 19/20) to avoid floating point edge cases.
        rank = (19 * n + 19) // 20
        latency = {
            "count": n,
            "min": vals[0],
            "max": vals[-1],
            "avg": round(sum(vals) / n, 2),
            "p95": vals[rank - 1],
        }
    else:
        latency = None

    top_messages = [
        {"message": msg, "count": cnt}
        for msg, cnt in sorted(templates.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    ]

    return {
        "total": total,
        "malformed": malformed,
        "by_level": {k: by_level[k] for k in sorted(by_level)},
        "by_service": {k: by_service[k] for k in sorted(by_service)},
        "latency_ms": latency,
        "top_messages": top_messages,
        "first_timestamp": fmt_ts(first),
        "last_timestamp": fmt_ts(last),
    }


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    file_path, opts = parse_args(argv)
    result = analyze(file_path, opts["since"], opts["until"], opts["level"], opts["top"])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
