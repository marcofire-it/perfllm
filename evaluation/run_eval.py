#!/usr/bin/env python
"""Runs the hidden tests on one or more submissions and saves the results.

Usage:
    python evaluation/run_eval.py --model gpt-5                 # every task present for that model
    python evaluation/run_eval.py --model gpt-5 --task 01       # a single task (prefix or full id)
    python evaluation/run_eval.py --all                         # every model in submissions/
    python evaluation/run_eval.py --model _reference            # validate the tests against the reference implementations

For each (model, task) it writes results/<model>/<task-id>.json and regenerates results/summary.md.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "evaluation"
SUBMISSIONS_DIR = ROOT / "submissions"
RESULTS_DIR = ROOT / "results"
REFERENCE_DIR = EVAL_DIR / "reference"

TASKS = {
    "01-logstats": {"required": ["logstats.py"], "level": 1},
    "02-dagrunner": {"required": ["dagrunner.py"], "level": 2},
    "03-minilang": {"required": ["minilang.py"], "level": 3},
}
MARKERS = ("core", "edge", "perf")
SUITE_TIMEOUT_S = 900


def resolve_task(arg: str) -> str:
    for tid in TASKS:
        if tid == arg or tid.startswith(arg):
            return tid
    sys.exit(f"unknown task: {arg} (available: {', '.join(TASKS)})")


def submission_root(model: str) -> Path:
    return REFERENCE_DIR if model == "_reference" else SUBMISSIONS_DIR / model


def run_pytest(task_id: str, sub_dir: Path) -> dict:
    """Runs pytest for the task against the given submission; returns a result dict."""
    env = dict(os.environ, PERFLLM_SUBMISSION_DIR=str(sub_dir), PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [
            sys.executable, "-m", "pytest", str(EVAL_DIR / task_id),
            "-q", "-p", "no:cacheprovider", "--rootdir", str(EVAL_DIR / task_id),
            f"--junitxml={junit}", "-o", "junit_family=xunit2",
        ]
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  timeout=SUITE_TIMEOUT_S, cwd=str(ROOT))
            timed_out = False
            output = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            output = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else "(timeout)"
        elapsed = time.perf_counter() - t0
        tests = parse_junit(junit) if junit.exists() else []

    by_marker = {m: {"passed": 0, "failed": 0} for m in MARKERS}
    by_marker["other"] = {"passed": 0, "failed": 0}
    for t in tests:
        m = t["marker"] if t["marker"] in MARKERS else "other"
        by_marker[m]["passed" if t["passed"] else "failed"] += 1
    passed = sum(1 for t in tests if t["passed"])
    total = len(tests)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_marker": by_marker,
        "elapsed_s": round(elapsed, 1),
        "timed_out": timed_out,
        "failed_tests": [t["name"] + (f" — {t['message']}" if t["message"] else "") for t in tests if not t["passed"]],
        "pytest_tail": "\n".join(output.strip().splitlines()[-15:]),
    }


def parse_junit(path: Path) -> list[dict]:
    """Extracts the testcases from the junit xml. The marker comes from the properties (see conftest hook) or from the name."""
    tree = ET.parse(path)
    out = []
    for tc in tree.iter("testcase"):
        name = tc.get("name", "")
        classname = tc.get("classname", "")
        failed = any(child.tag in ("failure", "error") for child in tc)
        skipped = any(child.tag == "skipped" for child in tc)
        message = ""
        for child in tc:
            if child.tag in ("failure", "error"):
                message = (child.get("message") or "").splitlines()[0][:200] if child.get("message") else ""
        marker = ""
        props = tc.find("properties")
        if props is not None:
            for p in props.iter("property"):
                if p.get("name") == "marker":
                    marker = p.get("value", "")
        if not marker:
            # fallback: test name starting with core_/edge_/perf_
            for m in MARKERS:
                if name.startswith(f"test_{m}_") or f"[{m}" in name:
                    marker = m
        out.append({"name": f"{classname}::{name}" if classname else name,
                    "passed": (not failed) and (not skipped), "skipped": skipped,
                    "marker": marker, "message": message})
    return out


def evaluate(model: str, task_id: str) -> dict:
    sub_dir = submission_root(model) / task_id
    spec = TASKS[task_id]
    result = {
        "model": model, "task": task_id, "level": spec["level"],
        "submission_dir": str(sub_dir), "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not sub_dir.is_dir():
        result.update(status="missing", passed=0, total=0, pass_rate=0.0, note="submission folder missing")
        return result
    missing = [f for f in spec["required"] if not (sub_dir / f).is_file()]
    if missing:
        result.update(status="missing_files", passed=0, total=0, pass_rate=0.0,
                      note=f"required files missing: {', '.join(missing)}")
        return result
    result["has_notes"] = (sub_dir / "NOTES.md").is_file()
    result["has_own_tests"] = any(p.name.startswith("test_") and p.suffix == ".py" for p in sub_dir.iterdir())
    result["status"] = "evaluated"
    result.update(run_pytest(task_id, sub_dir))
    return result


def save_result(res: dict) -> Path:
    out_dir = RESULTS_DIR / res["model"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{res['task']}.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def print_result(res: dict) -> None:
    head = f"[{res['model']}] {res['task']}"
    if res["status"] != "evaluated":
        print(f"{head}: {res['status']} — {res.get('note', '')}")
        return
    bm = res["by_marker"]
    parts = " ".join(f"{m}={bm[m]['passed']}/{bm[m]['passed'] + bm[m]['failed']}" for m in MARKERS)
    flag = " (TIMEOUT SUITE)" if res.get("timed_out") else ""
    print(f"{head}: {res['passed']}/{res['total']} ({res['pass_rate'] * 100:.0f}%)  {parts}  {res['elapsed_s']}s{flag}")
    for f in res["failed_tests"][:40]:
        print(f"    FAIL {f}")
    if len(res["failed_tests"]) > 40:
        print(f"    ... and {len(res['failed_tests']) - 40} more")


def write_summary() -> None:
    rows = []
    for model_dir in sorted(RESULTS_DIR.iterdir()) if RESULTS_DIR.is_dir() else []:
        if not model_dir.is_dir():
            continue
        for tid in TASKS:
            p = model_dir / f"{tid}.json"
            if p.is_file():
                rows.append(json.loads(p.read_text(encoding="utf-8")))
    models = sorted({r["model"] for r in rows})
    lines = ["# Automatic test summary", "",
             "Percentage of hidden tests passed (core / edge / perf in brackets). "
             "The qualitative evaluation is in the per-model scorecards.", "",
             "| Model | " + " | ".join(TASKS) + " | Average |", "|---|" + "---|" * (len(TASKS) + 1)]
    for m in models:
        cells, rates = [], []
        for tid in TASKS:
            r = next((x for x in rows if x["model"] == m and x["task"] == tid), None)
            if r is None:
                cells.append("—")
            elif r["status"] != "evaluated":
                cells.append(f"0% ({r['status']})")
                rates.append(0.0)
            else:
                bm = r["by_marker"]
                detail = "/".join(f"{bm[k]['passed']}:{bm[k]['passed'] + bm[k]['failed']}" for k in MARKERS)
                cells.append(f"{r['pass_rate'] * 100:.0f}% ({detail})")
                rates.append(r["pass_rate"])
        avg = f"{sum(rates) / len(rates) * 100:.0f}%" if rates else "—"
        lines.append(f"| {m} | " + " | ".join(cells) + f" | {avg} |")
    lines += ["", f"_Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}_", ""]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--model", help="folder name in submissions/ (or _reference)")
    g.add_argument("--all", action="store_true", help="evaluate every model in submissions/")
    ap.add_argument("--task", help="task id (01, 02, 03 or full name); default: all")
    ap.add_argument("--no-save", action="store_true", help="do not write results to disk")
    args = ap.parse_args()

    if args.all:
        models = sorted(p.name for p in SUBMISSIONS_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))
        if not models:
            sys.exit("no submissions in submissions/")
    else:
        models = [args.model]
    task_ids = [resolve_task(args.task)] if args.task else list(TASKS)

    for model in models:
        for tid in task_ids:
            if not args.task and not (submission_root(model) / tid).is_dir():
                continue  # without --task, silently skip tasks that were not submitted
            res = evaluate(model, tid)
            print_result(res)
            if not args.no_save:
                save_result(res)
    if not args.no_save:
        write_summary()
        print(f"\nSummary updated: {RESULTS_DIR / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
