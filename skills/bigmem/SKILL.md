---
name: bigmem
description: Persistent memory store for AI agents. Use to remember facts, recall stored information, search memory, and manage the memory store (bulk ops, cleanup, stats, etc.).
allowed-tools: Bash
context: fork
argument-hint: "<command> [args...] — e.g. 'put key value', 'search query', 'get key', 'stats'"
---

# bigmem — Persistent memory store

## Quick dispatch

Determine the intent from `$ARGUMENTS` and run the appropriate command:

**Store a fact** (`put`, `remember`, or arguments look like `<key> <value>`):
```bash
bigmem put $ARGUMENTS -q
```
For multi-line values use `--stdin`: `echo '<value>' | bigmem put <key> --stdin -q`
After storing, respond with only: "Remembered `<key>`."

**Retrieve by key** (argument is a single identifier, no spaces):
```bash
bigmem get $ARGUMENTS --raw
```

**Search** (argument has spaces, is a question, or is descriptive):
```bash
bigmem search "$ARGUMENTS"
```

**Filter by tag** (argument prefixed with `#` or `tag:`):
```bash
bigmem list --tags <tag-name>
```

**Any other command** (stats, list, delete, cleanup, export, import, batch, etc.):
```bash
bigmem $ARGUMENTS
```

**No arguments** — show what's available:
```bash
bigmem stats
echo "---"
bigmem list --limit 10 --keys-only
```

## Search behavior

- **Short queries (1-3 words):** implicit AND — all words must appear. Precise.
- **Long queries (4+ words):** auto-converts to OR after stripping stopwords. Broad recall.
- **`--exact` flag:** forces AND matching even for long queries.
- **FTS5 operators** (`AND`, `OR`, `NOT`, `NEAR`, `"..."`, `*`): pass through unchanged for full control.
- Try at most **2 searches** per concept. If both return empty, the fact doesn't exist — stop.

## Token efficiency

- **`--raw` on `get`** — value-only output, no metadata wrapper
- **Multi-key fetch:** `bigmem get key1 key2 key3` (one call, not three)
- **Search-then-get:** `search` first to find keys, then `get <key> --raw` for the specific value
- **`--keys-only` on `list`** — scan available keys without loading full values
- **`-q` on writes** — suppress confirmation noise
- **Batch reads:** for 5+ facts, pipe NDJSON get operations through `batch`

## Commands reference

| Command | Purpose |
|---------|---------|
| `put <key> <value>` | Store a fact (auto-wraps strings, always upserts) |
| `get <key> [key2...]` | Retrieve one or more facts |
| `exists <key>` | Check existence (exit 0=yes, 1=no) |
| `append <key> <value>` | Append to JSON array (atomic, creates if missing) |
| `search <query>` | Full-text search (FTS5; smart OR for 4+ words) |
| `list` | List facts with filters |
| `delete <key>` | Remove a fact |
| `cleanup` | Delete old/tagged facts (preserves `pin` tag) |
| `session-end <id>` | Clean up ephemeral session data |
| `export` | Export as NDJSON (--file, --tags) |
| `import --file <path>` | Import from NDJSON |
| `batch` | NDJSON bulk operations on stdin |
| `stats` | Database statistics |

## Useful flags

- `--db PATH` — use a different database
- `--namespace NS` — isolate facts by namespace
- `--pretty` — human-readable output
- `--raw` — value-only output on get
- `--keys-only` — list keys without values
- `--tags t1,t2` — tag filtering
- `--since T` / `--before T` — time-filtered queries (ISO 8601)
- `--ephemeral` — mark fact as session-scoped
- `--session ID` — associate fact with a session

## Tag conventions

| Tag | Meaning |
|-----|---------|
| `pin` | Survives cleanup (never auto-deleted) |
| `decision` | Architectural/design decisions |
| `preference` | User preferences |
| `debug` | Debugging findings |
| `context` | Task/project context |
| `blocker` | Known issues |

## Exit codes

- 0 = success
- 1 = not found
- 2 = usage error

Summarize results concisely for the parent context.
