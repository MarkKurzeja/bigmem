"""Shared pytest fixtures for BigMem eval suite."""

from __future__ import annotations

import json
import os
import shutil

import pytest

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DIR = os.path.join(EVAL_DIR, "golden")
GROUND_TRUTH_PATH = os.path.join(EVAL_DIR, "seed", "ground_truth.json")
REPORTS_DIR = os.path.join(EVAL_DIR, "reports")


def pytest_addoption(parser):
  parser.addoption(
    "--run-expensive",
    action="store_true",
    default=False,
    help="Run expensive multi-agent tests",
  )
  parser.addoption("--eval-model", default="sonnet", help="Model to use for eval (default: sonnet)")
  parser.addoption("--max-budget", type=float, default=0.50, help="Max budget per question in USD")


@pytest.fixture
def eval_model(request):
  return request.config.getoption("--eval-model")


@pytest.fixture
def max_budget(request):
  return request.config.getoption("--max-budget")


@pytest.fixture
def ground_truth():
  """Load ground truth questions."""
  with open(GROUND_TRUTH_PATH) as f:
    return json.load(f)


@pytest.fixture
def baseline_db(tmp_path):
  """Copy baseline golden DB to a temp directory for isolated testing."""
  src = os.path.join(GOLDEN_DIR, "baseline.db")
  if not os.path.exists(src):
    pytest.skip(
      "Golden baseline.db not found. Run: uv run python eval/seed/build_golden_db.py --tier baseline --output eval/golden/baseline.db"
    )
  dst = str(tmp_path / "test.db")
  shutil.copy2(src, dst)
  for suffix in ["-wal", "-shm"]:
    s = src + suffix
    if os.path.exists(s):
      shutil.copy2(s, dst + suffix)
  return dst


@pytest.fixture
def scale_db(tmp_path):
  """Copy scale golden DB to a temp directory for isolated testing."""
  src = os.path.join(GOLDEN_DIR, "scale.db")
  if not os.path.exists(src):
    pytest.skip(
      "Golden scale.db not found. Run: uv run python eval/seed/build_golden_db.py --tier scale --output eval/golden/scale.db"
    )
  dst = str(tmp_path / "test.db")
  shutil.copy2(src, dst)
  for suffix in ["-wal", "-shm"]:
    s = src + suffix
    if os.path.exists(s):
      shutil.copy2(s, dst + suffix)
  return dst


@pytest.fixture
def reports_dir():
  """Return the reports directory, creating it if needed."""
  os.makedirs(REPORTS_DIR, exist_ok=True)
  return REPORTS_DIR
