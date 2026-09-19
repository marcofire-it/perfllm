#!/usr/bin/env python
"""Extracts the files from a model's raw response in the format required by tasks/PROMPT.md.

Usage:
    python evaluation/split_response.py <raw_response.md> <destination_folder> [--force]

Recognises blocks:
    === FILE: name.py ===
    ...content...
    === END FILE ===

It also tolerates common variants: content wrapped in a ``` fence (removed), spaces around the name,
"=== FILE name ===" without the colon. Copies the raw response to <dest>/raw_response.md.
Does not overwrite existing files without --force.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BLOCK_RE = re.compile(
    r"^===\s*FILE:?\s*(?P<name>[^\n=]+?)\s*===\s*\n(?P<body>.*?)^===\s*END\s*FILE\s*===\s*$",
    re.MULTILINE | re.DOTALL,
)
FENCE_RE = re.compile(r"^```[\w+-]*\s*\n(?P<inner>.*?)\n```\s*$", re.DOTALL)


def strip_fence(body: str) -> str:
    m = FENCE_RE.match(body.strip("\n"))
    return m.group("inner") + "\n" if m else body


def main(argv: list[str]) -> int:
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    if len(args) != 2:
        print(__doc__)
        return 1
    src, dest = Path(args[0]), Path(args[1])
    text = src.read_text(encoding="utf-8")
    blocks = list(BLOCK_RE.finditer(text))
    if not blocks:
        print("no '=== FILE: ... ===' block found: the model did not follow the format. "
              "Extract the files by hand and note it in the scorecard (section B).")
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for m in blocks:
        name = m.group("name").strip().strip("`")
        if "/" in name or "\\" in name or name.startswith("."):
            print(f"  suspicious file name, skipped: {name!r}")
            continue
        target = dest / name
        if target.exists() and not force:
            print(f"  already exists, skipping (use --force): {target}")
            continue
        target.write_text(strip_fence(m.group("body")), encoding="utf-8", newline="\n")
        written.append(name)
    raw_target = dest / "raw_response.md"
    if src.resolve() != raw_target.resolve():
        shutil.copyfile(src, raw_target)
    print(f"wrote {len(written)} file(s) to {dest}: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
