# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is bigmem?

SQLite-backed persistent memory store for AI agents. Zero external dependencies — pure Python 3.10+ stdlib (sqlite3, json, argparse). Provides key-value storage with full-text search (FTS5), tagging, namespace isolation, and session management.

## Development Commands

```bash
uv sync                              # Install dependencies
uv run pytest tests/                 # Run all tests
uv run pytest tests/test_store.py -v # Run a single test module
uv run pytest tests/ -k "test_put"   # Run tests matching a name
uv run pytest tests/test_bench.py -v -s   # Benchmarks (with stdout)
uv run pytest tests/test_stress.py -v     # Concurrent stress tests
uv run bigmem version               # Run the CLI
```

Formatting uses `uv format` (ruff) with 2-space indentation. Run `uv format` before committing.

## Architecture

Four-layer design, each layer only calls the one below it:

```
CLI (cli.py) → Store API (store.py) → DB layer (db.py) → SQLite
                                        ↑
                                   models.py (Fact dataclass)
```

- **models.py** — `Fact` dataclass with `to_dict()`, `to_json()`, `from_row()` serialization. Composite primary key: `(key, namespace)`.
- **db.py** — `get_connection()` opens SQLite with hardened WAL-mode pragmas (64MB cache, 256MB mmap, 5s busy timeout). `init_db()` creates `facts` table + FTS5 virtual table with triggers to keep them in sync. Each CLI invocation opens, uses, and closes a connection (stateless).
- **store.py** — Core API: `put`, `get`, `list_facts`, `search`, `append`, `exists`, `delete`, `session_end`, `cleanup`, `stats`. All values are auto-normalized to JSON. `append` uses `BEGIN IMMEDIATE` transactions for concurrent safety.
- **cli.py** — argparse-based CLI with 14 subcommands. Compact JSON output by default. Supports batch operations via NDJSON on stdin.

**Entry point:** `bigmem = "bigmem.cli:main"` (defined in pyproject.toml). Also runnable via `python -m bigmem`.

## Key Design Decisions

- **Namespace isolation** — composite PK `(key, namespace)` allows parallel agents to use the same DB without conflicts
- **FTS5 triggers** — inserts/updates/deletes on `facts` table automatically propagate to the `facts_fts` full-text index
- **FTS5 smart search** — short queries (≤3 words) use implicit AND; long queries (4+ words) auto-convert to OR after stripping stopwords for better recall. Use `--exact` to force AND. Raw FTS5 operators (`AND`, `OR`, `NOT`, `NEAR`, `"..."`) pass through unchanged.
- **Tag storage** — tags stored as comma-separated string in SQLite, parsed to/from Python lists
- **Pinned facts** — facts tagged `pin` are never removed by `cleanup`
- **Ephemeral facts** — tied to a `session_id`, cleaned up via `session_end`

## CLI Quick Reference

```bash
bigmem put <key> <value> [--tags t1,t2] [--source agent-id] [-q]
bigmem get <key> [key2...] [--raw]
bigmem exists <key>
bigmem append <key> <value> [--tags t1,t2] [-q]
bigmem search <query> [--tags t]
bigmem list [--tags t] [--keys-only] [--session s] [--since T] [--before T]
bigmem delete <key>
bigmem cleanup [--before T] [--tags t]       # pinned facts always preserved
bigmem session-end <session-id>
bigmem export [--file path] [--tags t]
bigmem import --file path
echo '{"op":"put","key":"k","value":"v"}' | bigmem batch
bigmem stats
```

**Global flags:** `--db PATH` (default `~/.bigmem.db`), `--namespace NS` (default `default`), `--pretty`

**Exit codes:** 0 = success, 1 = not found, 2 = usage error

## Tag Conventions

`pin` (survives cleanup), `decision`, `preference`, `debug`, `context`, `blocker`

## Claude Code Integration

- `.claude/settings.json` configures a `SessionStart` hook that runs `reinject-memories.sh`
- Single `bigmem` skill in `.claude/skills/` and `skills/` (hardlinked) handles all memory operations: store, retrieve, search, bulk ops
