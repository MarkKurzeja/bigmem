---
name: bigmem
description: Full access to the bigmem memory store. Use for bulk operations, batch queries, stats, session cleanup, or any memory operation beyond simple remember/recall.
allowed-tools: Bash
context: fork
argument-hint: "<command> [args...]"
---

# bigmem — Full memory store access

Run any bigmem command. If `$ARGUMENTS` is provided, execute it directly:

```bash
bigmem $ARGUMENTS
```

If no arguments, show stats and recent entries:
```bash
bigmem stats
echo "---"
bigmem list --limit 10
```

## Available commands

| Command | Purpose |
|---------|---------|
| `put <key> <value>` | Store a fact (auto-wraps strings, always upserts) |
| `get <key> [key2...]` | Retrieve one or more facts |
| `list` | List facts with filters |
| `search <query>` | Full-text search |
| `delete <key>` | Remove a fact |
| `session-end <id>` | Clean up ephemeral session data |
| `batch` | NDJSON bulk operations on stdin |
| `stats` | Database statistics |

## Useful flags
- `--db PATH` — use a different database (for isolated workspaces)
- `--namespace NS` — isolate facts by namespace
- `--pretty` — human-readable output
- `-q` / `--quiet` — suppress put confirmation
- `--raw` — value-only output on get
- `--keys-only` — list keys without values
- `--tags t1,t2` — tag filtering

## Batch example
```bash
echo '{"op":"put","key":"a","value":"1"}
{"op":"put","key":"b","value":"2"}
{"op":"get","key":"a"}' | bigmem batch
```

Summarize results concisely for the parent context.
