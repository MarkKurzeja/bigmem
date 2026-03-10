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
| `exists <key>` | Check existence (exit 0=yes, 1=no) |
| `append <key> <value>` | Append to JSON array (atomic, creates if missing) |
| `search <query>` | Full-text search across key/value/tags |
| `list` | List facts with filters |
| `delete <key>` | Remove a fact |
| `cleanup` | Delete old/tagged facts (preserves `pin` tag) |
| `session-end <id>` | Clean up ephemeral session data |
| `export` | Export as NDJSON (--file, --tags) |
| `import --file <path>` | Import from NDJSON |
| `batch` | NDJSON bulk operations on stdin |
| `stats` | Database statistics |
| `version` | Show version |

## Useful flags

- `--db PATH` — use a different database (for isolated workspaces)
- `--namespace NS` — isolate facts by namespace
- `--pretty` — human-readable output
- `-q` / `--quiet` — suppress put confirmation
- `--raw` — value-only output on get
- `--keys-only` — list keys without values
- `--tags t1,t2` — tag filtering
- `--since T` / `--before T` — time-filtered queries (ISO 8601)
- `--ephemeral` — mark fact as session-scoped
- `--session ID` — associate fact with a session
- `--stdin` — read value from stdin (for multi-line content)

## Tag conventions

| Tag | Meaning |
|-----|---------|
| `pin` | Survives cleanup (never auto-deleted) |
| `decision` | Architectural/design decisions |
| `preference` | User preferences |
| `debug` | Debugging findings |
| `context` | Task/project context |
| `blocker` | Known issues |

## Common patterns

**Pin critical facts:**
```bash
bigmem put project_arch "monorepo, React frontend, FastAPI backend" --tags pin
```

**Accumulate findings without read-modify-write:**
```bash
bigmem append findings "found XSS in auth.py" -q
bigmem append findings "SQL injection in search" -q
bigmem get findings --raw
```

**Batch operations (NDJSON on stdin):**
```bash
echo '{"op":"put","key":"a","value":"1"}
{"op":"put","key":"b","value":"2"}
{"op":"get","key":"a"}' | bigmem batch
```

**Namespace isolation for parallel agents:**
```bash
bigmem --namespace agent-1 put findings "..."
bigmem --namespace agent-2 put findings "..."
```

**Use `-q` on writes** to avoid adding confirmation noise to context:
```bash
bigmem put status "running task 3" -q
```

**Use `--raw` for piping** to avoid JSON parsing overhead:
```bash
VALUE=$(bigmem get config --raw)
```

**Multi-key fetch** reduces subprocess calls:
```bash
bigmem get user_name user_role user_prefs
```

**Quick existence check** without parsing a full fact:
```bash
bigmem exists config && echo "config is set"
```

**Time-filtered queries** for resuming work:
```bash
bigmem list --since 2025-03-10T00:00:00Z
bigmem list --before 2025-03-09T00:00:00Z --tags debug
```

**Ephemeral session memory** for scratch data that auto-cleans:
```bash
bigmem put scratch "temp" --ephemeral --session $SESSION_ID
bigmem session-end $SESSION_ID
```

**Cleanup old facts (pinned facts preserved):**
```bash
bigmem cleanup --before 2025-01-01T00:00:00Z
bigmem cleanup --tags debug
```

**Export/import for backups:**
```bash
bigmem export --file backup.ndjson
bigmem --db new.db import --file backup.ndjson
```

## Exit codes

- 0 = success
- 1 = not found
- 2 = usage error

Summarize results concisely for the parent context.
