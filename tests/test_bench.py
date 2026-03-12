"""Benchmarks for bigmem operations.

Run with: uv run pytest tests/test_bench.py -v -s
The -s flag is important to see the timing output.

These are real pytest tests (they assert correctness) but also print
timing data so you can see the cost of each operation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from bigmem.db import get_connection, init_db, close_connection
from bigmem.store import put, get, list_facts, search, delete, append, exists


def _timed(label: str, fn, n: int) -> float:
  """Run fn() n times, print and return total elapsed seconds."""
  start = time.perf_counter()
  for _ in range(n):
    fn()
  elapsed = time.perf_counter() - start
  per_op = elapsed / n * 1000  # ms
  ops_sec = n / elapsed if elapsed > 0 else float("inf")
  print(f"  {label}: {n} ops in {elapsed:.3f}s ({per_op:.2f} ms/op, {ops_sec:.0f} ops/s)")
  return elapsed


# ── In-process benchmarks (library calls, no subprocess overhead) ────────


class TestInProcessBenchmarks:
  """Benchmark raw library performance without subprocess overhead."""

  def test_bench_open_close(self, tmp_path):
    """Cost of opening and closing a connection."""
    db = str(tmp_path / "bench.db")
    # First open to create the DB
    conn = get_connection(db)
    init_db(conn)
    close_connection(conn)

    def open_close():
      c = get_connection(db)
      close_connection(c)

    print()
    _timed("open+close", open_close, 200)

  def test_bench_open_init_close(self, tmp_path):
    """Cost of open + init_db + close (full CLI cycle)."""
    db = str(tmp_path / "bench.db")

    def full_cycle():
      c = get_connection(db)
      init_db(c)
      close_connection(c)

    print()
    _timed("open+init+close", full_cycle, 200)

  def test_bench_put(self, tmp_path):
    """Cost of put (upsert) operations."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    i = [0]

    def do_put():
      put(conn, f"key-{i[0]}", f"value-{i[0]}")
      i[0] += 1

    print()
    _timed("put (distinct keys)", do_put, 1000)

    # Upsert same key
    def do_upsert():
      put(conn, "same-key", f"value-{i[0]}")
      i[0] += 1

    _timed("put (same key upsert)", do_upsert, 1000)
    close_connection(conn)

  def test_bench_get(self, tmp_path):
    """Cost of get (point lookup) operations."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    # Seed data
    for j in range(1000):
      put(conn, f"key-{j}", f"value-{j}")

    i = [0]

    def do_get():
      get(conn, f"key-{i[0] % 1000}")
      i[0] += 1

    print()
    _timed("get (1000 keys seeded)", do_get, 5000)

    # Miss
    def do_get_miss():
      get(conn, "nonexistent")

    _timed("get (miss)", do_get_miss, 5000)
    close_connection(conn)

  def test_bench_exists(self, tmp_path):
    """Cost of exists check."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    for j in range(1000):
      put(conn, f"key-{j}", f"value-{j}")

    i = [0]

    def do_exists():
      exists(conn, f"key-{i[0] % 1000}")
      i[0] += 1

    print()
    _timed("exists (hit)", do_exists, 5000)

    def do_exists_miss():
      exists(conn, "nonexistent")

    _timed("exists (miss)", do_exists_miss, 5000)
    close_connection(conn)

  def test_bench_list(self, tmp_path):
    """Cost of list operations at different scales."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    for j in range(1000):
      put(conn, f"key-{j}", f"value-{j}", tags="bench" if j % 2 == 0 else "other")

    print()
    _timed("list (limit=100, 1000 rows)", lambda: list_facts(conn, limit=100), 500)
    _timed("list (limit=10)", lambda: list_facts(conn, limit=10), 500)
    _timed("list (tag filter)", lambda: list_facts(conn, tags="bench", limit=100), 500)
    close_connection(conn)

  def test_bench_search(self, tmp_path):
    """Cost of FTS search at different scales."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    for j in range(1000):
      put(conn, f"doc-{j}", f"the quick brown fox jumps over lazy dog number {j}")

    print()
    _timed("search (FTS, 1000 docs)", lambda: search(conn, "quick brown"), 500)
    _timed("search (FTS, limit=10)", lambda: search(conn, "quick brown", limit=10), 500)
    _timed("search (FTS, no results)", lambda: search(conn, "nonexistent"), 500)
    close_connection(conn)

  def test_bench_delete(self, tmp_path):
    """Cost of delete operations."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    for j in range(1000):
      put(conn, f"key-{j}", f"value-{j}")

    i = [0]

    def do_delete():
      delete(conn, f"key-{i[0]}")
      i[0] += 1

    print()
    _timed("delete (1000 keys)", do_delete, 1000)
    close_connection(conn)

  def test_bench_append(self, tmp_path):
    """Cost of append (read-modify-write with BEGIN IMMEDIATE)."""
    db = str(tmp_path / "bench.db")
    conn = get_connection(db)
    init_db(conn)

    i = [0]

    def do_append():
      append(conn, "log", f"entry-{i[0]}")
      i[0] += 1

    print()
    _timed("append (growing list)", do_append, 200)
    # Verify correctness
    fact = get(conn, "log")
    val = json.loads(fact.value)
    assert len(val) == 200
    close_connection(conn)


# ── Subprocess benchmarks (real CLI cost) ─────────────────────────────────


class TestSubprocessBenchmarks:
  """Benchmark actual CLI invocations (subprocess overhead included)."""

  def test_bench_cli_put_get_cycle(self, tmp_path):
    """Cost of a full put + get cycle via CLI subprocess."""
    db = str(tmp_path / "bench.db")

    def cli_put(i):
      subprocess.run(
        [
          sys.executable,
          "-m",
          "bigmem",
          "--db",
          db,
          "put",
          f"key-{i}",
          f"value-{i}",
          "-q",
        ],
        capture_output=True,
        timeout=10,
      )

    def cli_get(i):
      subprocess.run(
        [sys.executable, "-m", "bigmem", "--db", db, "get", f"key-{i}"],
        capture_output=True,
        timeout=10,
      )

    n = 50
    print()

    # Put
    start = time.perf_counter()
    for i in range(n):
      cli_put(i)
    put_elapsed = time.perf_counter() - start
    print(f"  CLI put: {n} ops in {put_elapsed:.3f}s ({put_elapsed / n * 1000:.1f} ms/op)")

    # Get
    start = time.perf_counter()
    for i in range(n):
      cli_get(i)
    get_elapsed = time.perf_counter() - start
    print(f"  CLI get: {n} ops in {get_elapsed:.3f}s ({get_elapsed / n * 1000:.1f} ms/op)")

    # Batch (amortized)
    lines = "\n".join(
      json.dumps({"op": "put", "key": f"batch-{i}", "value": f"v-{i}"}) for i in range(n)
    )
    start = time.perf_counter()
    r = subprocess.run(
      [sys.executable, "-m", "bigmem", "--db", db, "batch"],
      input=lines,
      capture_output=True,
      text=True,
      timeout=30,
    )
    batch_elapsed = time.perf_counter() - start
    print(
      f"  CLI batch ({n} puts): {batch_elapsed:.3f}s ({batch_elapsed / n * 1000:.1f} ms/op amortized)"
    )
    print(f"  Batch speedup vs individual puts: {put_elapsed / batch_elapsed:.1f}x")

    assert r.returncode == 0

  def test_bench_cli_search(self, tmp_path):
    """Cost of CLI search including subprocess startup."""
    db = str(tmp_path / "bench.db")

    # Seed via batch
    lines = "\n".join(
      json.dumps(
        {
          "op": "put",
          "key": f"doc-{i}",
          "value": f"important finding number {i}",
        }
      )
      for i in range(100)
    )
    subprocess.run(
      [sys.executable, "-m", "bigmem", "--db", db, "batch"],
      input=lines,
      capture_output=True,
      text=True,
      timeout=30,
    )

    n = 20
    start = time.perf_counter()
    for _ in range(n):
      subprocess.run(
        [
          sys.executable,
          "-m",
          "bigmem",
          "--db",
          db,
          "search",
          "important finding",
        ],
        capture_output=True,
        timeout=10,
      )
    elapsed = time.perf_counter() - start
    print()
    print(f"  CLI search: {n} ops in {elapsed:.3f}s ({elapsed / n * 1000:.1f} ms/op)")

  def test_bench_cli_stats(self, tmp_path):
    """Cost of stats command (aggregation query)."""
    db = str(tmp_path / "bench.db")

    # Seed
    lines = "\n".join(
      json.dumps(
        {
          "op": "put",
          "key": f"k-{i}",
          "value": f"v-{i}",
          "tags": f"tag-{i % 5}",
        }
      )
      for i in range(500)
    )
    subprocess.run(
      [sys.executable, "-m", "bigmem", "--db", db, "batch"],
      input=lines,
      capture_output=True,
      text=True,
      timeout=30,
    )

    n = 20
    start = time.perf_counter()
    for _ in range(n):
      subprocess.run(
        [sys.executable, "-m", "bigmem", "--db", db, "stats"],
        capture_output=True,
        timeout=10,
      )
    elapsed = time.perf_counter() - start
    print()
    print(f"  CLI stats (500 rows): {n} ops in {elapsed:.3f}s ({elapsed / n * 1000:.1f} ms/op)")
