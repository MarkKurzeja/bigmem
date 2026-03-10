---
name: docs-bigmem
description: Write and maintain bigmem documentation. Use when creating, editing, or reviewing docs for bigmem — the SQLite-backed memory store for AI agents. Knows the full CLI surface, architecture, and usage patterns.
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
argument-hint: "[topic-or-task]"
---

# bigmem documentation skill

You are writing documentation for **bigmem**, a zero-dependency SQLite-backed memory store for AI agents.

## Project facts

- CLI entry point: `bigmem` (installed via `pip install .` or `uv pip install .`)
- Source: `src/bigmem/` — `cli.py`, `store.py`, `db.py`, `models.py`
- Database: SQLite with WAL mode, FTS5 full-text search
- No runtime dependencies
- Python >=3.10

## CLI surface (14 commands)

```
put <key> <value>           Store/upsert a fact (auto-wraps plain strings as JSON)
get <key> [key2...]         Retrieve facts (--raw for value-only)
exists <key>                Check existence (exit 0=yes, 1=no)
append <key> <value>        Append to JSON array (atomic, creates if missing)
search <query>              Full-text search across key/value/tags
list                        List facts (--tags, --keys-only, --session, --since, --before)
delete <key>                Remove a fact
cleanup                     Delete old/tagged facts (preserves "pin" tag)
session-end <session-id>    Delete ephemeral session facts
export                      Export as NDJSON (--file, --tags)
import --file <path>        Import from NDJSON
batch                       NDJSON bulk operations on stdin
stats                       Database statistics
version                     Show version
```

**Global flags:** `--db PATH`, `--namespace NS`, `--pretty`
**Write flags:** `-q`/`--quiet`, `--tags t1,t2`, `--source agent-id`, `--ephemeral`, `--session ID`, `--stdin`
**Read flags:** `--raw`, `--keys-only`, `--limit N`

## Tag conventions

| Tag | Meaning |
|-----|---------|
| `pin` | Survives cleanup (never auto-deleted) |
| `decision` | Architectural/design decisions |
| `preference` | User preferences |
| `debug` | Debugging findings |
| `context` | Task/project context |
| `blocker` | Known issues |

## Architecture notes

- **Data model:** `Fact` dataclass with key, namespace, value (JSON string), tags (comma-separated), source, session, ephemeral flag, created_at, updated_at
- **Primary key:** `(key, namespace)` — upserts on conflict
- **FTS:** Virtual FTS5 table synced via triggers on insert/update/delete
- **Atomicity:** `append` uses `BEGIN IMMEDIATE` to prevent race conditions
- **Cleanup safety:** Always preserves facts tagged `pin`

## Documentation guidelines

1. **Be concise.** Agents read docs — every token costs context. Prefer tables and code blocks over prose.
2. **Show, don't tell.** Lead with runnable examples, follow with explanation only if needed.
3. **Use exit codes.** Document `0 = success`, `1 = not found`, `2 = usage error` — agents rely on these.
4. **Audience is AI agents and their developers.** Skip "getting started" fluff. Assume the reader knows CLI tools and SQLite.
5. **Keep examples copy-pasteable.** No placeholder values that would break if run literally.
6. **Cross-reference the source.** When documenting behavior, note the source file (e.g., `store.py:append`).
7. **Document flags inline with commands**, not in a separate section — readers look up one command at a time.

## When writing new docs

- Read the relevant source files first (`src/bigmem/cli.py`, `src/bigmem/store.py`) to ensure accuracy.
- Check the root `CLAUDE.md` for existing documentation to avoid duplication.
- Place new docs in `docs/` with descriptive filenames (e.g., `docs/batch-operations.md`).
- If updating existing docs, preserve the established tone and format.
