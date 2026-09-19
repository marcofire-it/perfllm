"""Shared conftest (copied into every evaluation/<task>/conftest.py).

The submission under test is given by the PERFLLM_SUBMISSION_DIR environment variable
(absolute path of the folder holding the files delivered by the model).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "core: basic functionality required by the spec")
    config.addinivalue_line("markers", "edge: edge cases, robustness, errors")
    config.addinivalue_line("markers", "perf: performance / concurrency")


@pytest.fixture(scope="session")
def submission_dir() -> Path:
    raw = os.environ.get("PERFLLM_SUBMISSION_DIR")
    if not raw:
        pytest.fail("PERFLLM_SUBMISSION_DIR not set (use evaluation/run_eval.py)")
    p = Path(raw).resolve()
    if not p.is_dir():
        pytest.fail(f"submission dir not found: {p}")
    return p


def load_module_from(submission_dir: Path, filename: str):
    """Imports <submission_dir>/<filename> as an isolated module (without touching sys.path)."""
    path = submission_dir / filename
    if not path.is_file():
        pytest.fail(f"required file missing from the submission: {filename}")
    name = f"perfllm_sub_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _record_marker(request, record_property):
    """Records the marker (core/edge/perf) in the junit xml, read by run_eval.py."""
    for m in ("core", "edge", "perf"):
        if request.node.get_closest_marker(m) is not None:
            record_property("marker", m)
            break
