"""Stress tests for concurrent multi-process access to bigmem.

These tests spawn multiple subprocesses hitting the same database
simultaneously to verify WAL mode, busy_timeout, and locking behavior
under contention.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

import pytest


def _bigmem(*args: str, db: str, namespace: str = "default") -> subprocess.CompletedProcess:
  return subprocess.run(
    [sys.executable, "-m", "bigmem", "--db", db, "--namespace", namespace] + list(args),
    capture_output=True,
    text=True,
    timeout=30,
  )


def _put(db: str, key: str, value: str, namespace: str = "default", tags: str = "") -> dict:
  cmd = [
    sys.executable,
    "-m",
    "bigmem",
    "--db",
    db,
    "--namespace",
    namespace,
    "put",
    key,
    value,
  ]
  if tags:
    cmd += ["--tags", tags]
  r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
  return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def _get(db: str, key: str, namespace: str = "default") -> dict:
  r = subprocess.run(
    [
      sys.executable,
      "-m",
      "bigmem",
      "--db",
      db,
      "--namespace",
      namespace,
      "get",
      key,
    ],
    capture_output=True,
    text=True,
    timeout=30,
  )
  return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def _append(db: str, key: str, value: str, namespace: str = "default") -> dict:
  r = subprocess.run(
    [
      sys.executable,
      "-m",
      "bigmem",
      "--db",
      db,
      "--namespace",
      namespace,
      "append",
      key,
      value,
    ],
    capture_output=True,
    text=True,
    timeout=30,
  )
  return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def _search(db: str, query: str, namespace: str = "default") -> dict:
  r = subprocess.run(
    [
      sys.executable,
      "-m",
      "bigmem",
      "--db",
      db,
      "--namespace",
      namespace,
      "search",
      query,
    ],
    capture_output=True,
    text=True,
    timeout=30,
  )
  return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def _list_keys(db: str, namespace: str = "default") -> dict:
  r = subprocess.run(
    [
      sys.executable,
      "-m",
      "bigmem",
      "--db",
      db,
      "--namespace",
      namespace,
      "list",
      "--keys-only",
    ],
    capture_output=True,
    text=True,
    timeout=30,
  )
  return {
    "rc": r.returncode,
    "keys": json.loads(r.stdout) if r.returncode == 0 else [],
  }


def _consume_task(args: tuple) -> dict:
  """Read a task and mark it done — used by producer/consumer test."""
  db, i = args
  r = _get(db, f"task-{i}", namespace="tasks")
  if r["rc"] != 0:
    return {"ok": False, "error": "not found", "i": i}
  task = json.loads(r["stdout"])
  done = json.dumps({"status": "done", "data": task["value"]["data"]})
  w = _put(db, f"task-{i}", done, namespace="tasks", tags="done")
  return {"ok": w["rc"] == 0, "i": i}


# ── Heavy concurrent writes ──────────────────────────────────────────────


class TestConcurrentWrites:
  """Many processes writing distinct keys simultaneously."""

  def test_parallel_puts_no_conflicts(self, tmp_path):
    db = str(tmp_path / "stress.db")
    n = 50

    # Initialize the database first
    _bigmem("stats", db=db)

    with ProcessPoolExecutor(max_workers=8) as pool:
      futures = {pool.submit(_put, db, f"key-{i}", f"value-{i}"): i for i in range(n)}
      results = {}
      for future in as_completed(futures):
        i = futures[future]
        results[i] = future.result()

    # All writes should succeed
    failures = {i: r for i, r in results.items() if r["rc"] != 0}
    assert not failures, f"Failed writes: {failures}"

    # Verify all keys exist
    r = _bigmem("stats", db=db)
    stats = json.loads(r.stdout)
    assert stats["total_facts"] == n

  def test_parallel_puts_same_key_upsert(self, tmp_path):
    """Multiple processes upserting the same key — last writer wins."""
    db = str(tmp_path / "stress.db")
    n = 30

    _bigmem("stats", db=db)

    with ProcessPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(_put, db, "contended-key", f"value-{i}") for i in range(n)]
      results = [f.result() for f in futures]

    # All should succeed (upsert, not insert)
    failures = [r for r in results if r["rc"] != 0]
    assert not failures, f"Failed writes: {failures}"

    # Key should exist with one of the values
    r = _get(db, "contended-key")
    assert r["rc"] == 0
    fact = json.loads(r["stdout"])
    assert fact["value"].startswith("value-")


# ── Concurrent reads and writes ──────────────────────────────────────────


class TestConcurrentReadsWrites:
  """Readers and writers operating simultaneously (WAL mode test)."""

  def test_reads_dont_block_writes(self, tmp_path):
    db = str(tmp_path / "stress.db")
    n_writers = 20
    n_readers = 20

    # Seed some initial data
    _bigmem("stats", db=db)
    for i in range(10):
      _put(db, f"seed-{i}", f"seed-value-{i}")

    with ProcessPoolExecutor(max_workers=8) as pool:
      write_futures = [
        pool.submit(_put, db, f"new-{i}", f"new-value-{i}") for i in range(n_writers)
      ]
      read_futures = [pool.submit(_get, db, f"seed-{i % 10}") for i in range(n_readers)]
      all_futures = write_futures + read_futures

      results = [f.result() for f in all_futures]

    write_results = results[:n_writers]
    read_results = results[n_writers:]

    write_failures = [r for r in write_results if r["rc"] != 0]
    read_failures = [r for r in read_results if r["rc"] != 0]

    assert not write_failures, f"Write failures: {write_failures}"
    assert not read_failures, f"Read failures: {read_failures}"


# ── Namespace isolation under concurrency ────────────────────────────────


class TestConcurrentNamespaces:
  """Multiple agents writing to different namespaces simultaneously."""

  def test_namespace_isolation_concurrent(self, tmp_path):
    db = str(tmp_path / "stress.db")
    n_agents = 5
    n_facts_per_agent = 10

    _bigmem("stats", db=db)

    with ProcessPoolExecutor(max_workers=8) as pool:
      futures = []
      for agent in range(n_agents):
        ns = f"agent-{agent}"
        for i in range(n_facts_per_agent):
          futures.append(
            pool.submit(
              _put,
              db,
              f"fact-{i}",
              f"agent-{agent}-value-{i}",
              namespace=ns,
            )
          )
      results = [f.result() for f in futures]

    failures = [r for r in results if r["rc"] != 0]
    assert not failures, f"Failed writes: {failures}"

    # Each namespace should have its own facts
    for agent in range(n_agents):
      ns = f"agent-{agent}"
      r = _bigmem("list", "--keys-only", db=db, namespace=ns)
      keys = json.loads(r.stdout)
      assert len(keys) == n_facts_per_agent, (
        f"Namespace {ns}: expected {n_facts_per_agent}, got {len(keys)}"
      )


# ── Append under concurrency (read-modify-write) ────────────────────────


class TestConcurrentAppend:
  """append() does read-then-write — test it under contention."""

  def test_concurrent_appends_to_same_key(self, tmp_path):
    db = str(tmp_path / "stress.db")
    n = 20

    _bigmem("stats", db=db)

    with ProcessPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(_append, db, "log", f"entry-{i}") for i in range(n)]
      results = [f.result() for f in futures]

    failures = [r for r in results if r["rc"] != 0]
    assert not failures, f"Failed appends: {failures}"

    # The final value should be a list (though order is non-deterministic
    # and some entries may be lost due to race conditions in read-modify-write)
    r = _get(db, "log")
    assert r["rc"] == 0
    fact = json.loads(r["stdout"])
    assert isinstance(fact["value"], list)
    # With BEGIN IMMEDIATE, all appends should succeed and be present
    assert len(fact["value"]) == n, (
      f"Expected {n} entries but got {len(fact['value'])} — possible race condition in append"
    )


# ── Search under write load ──────────────────────────────────────────────


class TestConcurrentSearch:
  """FTS search while writes are happening."""

  def test_search_during_writes(self, tmp_path):
    db = str(tmp_path / "stress.db")

    _bigmem("stats", db=db)

    # Seed searchable data
    for i in range(20):
      _put(db, f"doc-{i}", f"important finding number {i}", tags="research")

    with ProcessPoolExecutor(max_workers=8) as pool:
      # Writers adding more data
      write_futures = [pool.submit(_put, db, f"extra-{i}", f"extra data {i}") for i in range(20)]
      # Readers searching
      search_futures = [pool.submit(_search, db, "important finding") for _ in range(10)]

      write_results = [f.result() for f in write_futures]
      search_results = [f.result() for f in search_futures]

    write_failures = [r for r in write_results if r["rc"] != 0]
    assert not write_failures, f"Write failures: {write_failures}"

    # All searches should succeed (WAL allows concurrent reads)
    search_failures = [r for r in search_results if r["rc"] != 0]
    assert not search_failures, f"Search failures: {search_failures}"

    # Each search should find results
    for r in search_results:
      results = json.loads(r["stdout"])
      assert len(results) > 0, "Search returned no results"


# ── Cross-process communication pattern ──────────────────────────────────


class TestCrossProcessCommunication:
  """Simulate agents communicating through shared bigmem keys."""

  def test_producer_consumer_pattern(self, tmp_path):
    """One agent produces work items, another consumes them."""
    db = str(tmp_path / "stress.db")
    n_items = 15

    _bigmem("stats", db=db)

    # Producer writes work items
    for i in range(n_items):
      _put(
        db,
        f"task-{i}",
        json.dumps({"status": "pending", "data": f"work-{i}"}),
        namespace="tasks",
        tags="pending",
      )

    # Consumer reads and marks them done (concurrently)
    with ProcessPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(_consume_task, (db, i)) for i in range(n_items)]
      results = [f.result() for f in futures]

    failures = [r for r in results if not r["ok"]]
    assert not failures, f"Consumer failures: {failures}"

    # All tasks should be marked done
    r = _bigmem("list", "--tags", "done", "--keys-only", db=db, namespace="tasks")
    done_keys = json.loads(r.stdout)
    assert len(done_keys) == n_items

  def test_channel_broadcast(self, tmp_path):
    """Multiple agents reading from a shared channel while one writes."""
    db = str(tmp_path / "stress.db")
    n_messages = 10
    n_readers = 5

    _bigmem("stats", db=db)

    # Broadcaster writes messages
    for i in range(n_messages):
      _put(db, f"msg-{i}", f"broadcast message {i}", namespace="channel")

    # Multiple readers simultaneously list the channel
    with ProcessPoolExecutor(max_workers=n_readers) as pool:
      futures = [pool.submit(_list_keys, db, "channel") for _ in range(n_readers)]
      results = [f.result() for f in futures]

    for r in results:
      assert r["rc"] == 0
      assert len(r["keys"]) == n_messages
