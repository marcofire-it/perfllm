#!/usr/bin/env python
"""Creates the working folders for the models (outside perfllm) and collects the results.

    python evaluation/arena.py prepare gpt-5 gemini-3-pro claude-opus-5
        creates ../perfllm-arena/<model>/<task-id>/TASK.md  (PROMPT + TASK concatenated)
        and prints the sentence to give each model.

    python evaluation/arena.py collect gpt-5          (or: collect --all)
        copies the files produced in ../perfllm-arena/<model>/<task-id>/ to submissions/<model>/<task-id>/
        excluding TASK.md, __pycache__ and hidden folders. If it finds a raw_response.md with
        === FILE: === blocks and no .py file, it extracts them with split_response.py.

The arena lives OUTSIDE the benchmark repo: a model with filesystem access must not be able to
read evaluation/ (hidden tests and reference solutions).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
ARENA = ROOT.parent / "perfllm-arena"
SUBMISSIONS = ROOT / "submissions"
TASK_IDS = ["01-logstats", "02-dagrunner", "03-minilang"]
SKIP_NAMES = {"TASK.md", "__pycache__", ".pytest_cache"}


def prepare(models: list[str]) -> None:
    prompt = (TASKS_DIR / "PROMPT.md").read_text(encoding="utf-8")
    for model in models:
        for tid in TASK_IDS:
            d = ARENA / model / tid
            d.mkdir(parents=True, exist_ok=True)
            task = (TASKS_DIR / tid / "TASK.md").read_text(encoding="utf-8")
            (d / "TASK.md").write_text(prompt + "\n" + task, encoding="utf-8")
    print(f"Arena created in: {ARENA}\n")
    print("For each model and task, open a NEW chat/session in the folder below and say ONLY this:\n")
    for model in models:
        for tid in TASK_IDS:
            print(f"  [{model} / {tid}]  folder: {ARENA / model / tid}")
    print("\n  Sentence (models that can read and write files, e.g. Claude Code / Codex / Cursor):")
    print('    "Read the file TASK.md in this folder and carry out the task. Create the required files in this')
    print('     same folder (in this case the === FILE === block format is not needed). Do not leave')
    print('     the folder and do not ask questions: document your assumptions in NOTES.md."')
    print("\n  Sentence (chats without file access, e.g. web interface):")
    print('    paste the full content of TASK.md, adding nothing else; save the complete response')
    print("    as raw_response.md in the same arena folder.")
    print(f"\nWhen they are done:  python evaluation/arena.py collect --all")


def collect(models: list[str]) -> None:
    if models == ["--all"]:
        models = sorted(p.name for p in ARENA.iterdir() if p.is_dir()) if ARENA.is_dir() else []
    for model in models:
        for tid in TASK_IDS:
            src = ARENA / model / tid
            if not src.is_dir():
                continue
            files = [p for p in src.iterdir() if p.name not in SKIP_NAMES and not p.name.startswith(".")]
            if not files:
                print(f"[{model}] {tid}: empty, skipping")
                continue
            dest = SUBMISSIONS / model / tid
            dest.mkdir(parents=True, exist_ok=True)
            copied = []
            for p in files:
                if p.is_dir():
                    shutil.copytree(p, dest / p.name, dirs_exist_ok=True)
                else:
                    shutil.copyfile(p, dest / p.name)
                copied.append(p.name)
            print(f"[{model}] {tid}: copied {', '.join(copied)}")
            raw = dest / "raw_response.md"
            if raw.is_file() and not any(p.suffix == ".py" for p in dest.iterdir()):
                subprocess.run([sys.executable, str(ROOT / "evaluation" / "split_response.py"),
                                str(raw), str(dest)], check=False)
    print(f"\nYou can now evaluate:  python evaluation/run_eval.py --all")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("prepare", "collect"):
        print(__doc__)
        return 1
    if argv[0] == "prepare":
        bad = [m for m in argv[1:] if not m or " " in m or m.startswith("_")]
        if bad:
            print(f"invalid model names (no spaces, no leading _): {bad}")
            return 1
        prepare(argv[1:])
    else:
        collect(argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
