# bigmem — SQLite-backed memory store for AI agents

## Quick CLI Reference

```bash
bigmem put <key> <value> [--tags t1,t2] [--source agent-id] [-q]
bigmem get <key> [key2...] [--raw]
bigmem exists <key>
bigmem append <key> <value> [--tags t1,t2] [-q]
bigmem search <query> [--tags t]
bigmem list [--tags t] [--keys-only] [--session s] [--since T] [--before T]
bigmem delete <key>
bigmem cleanup [--before T] [--tags t]
bigmem session-end <session-id>
bigmem export [--file path] [--tags t]
bigmem import --file path
echo '{"op":"put","key":"k","value":"v"}' | bigmem batch
bigmem stats
bigmem version
```

## Global flags
- `--db PATH` — database file (default: `~/.bigmem.db`). Use separate paths for parallel agents.
- `--namespace NS` — isolate facts by namespace (default: `default`)
- `--pretty` — pretty-print JSON (default: compact for token efficiency)

## Context management patterns

**Pin critical facts** so they survive cleanup:
```bash
bigmem put project_arch "monorepo, React frontend, FastAPI backend" --tags pin
```

**Use `-q` on writes** to avoid adding confirmation noise to context:
```bash
bigmem put status "running task 3" -q
```

**Use `--raw` for piping** to avoid parsing overhead:
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

**Accumulate findings** without read-modify-write:
```bash
bigmem append findings "found XSS in auth.py" -q
bigmem append findings "SQL injection in search" -q
bigmem get findings --raw   # → ["found XSS in auth.py", "SQL injection in search"]
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

**Batch operations** for bulk work (NDJSON on stdin, supports all ops):
```bash
echo '{"op":"put","key":"a","value":"1"}
{"op":"append","key":"log","value":"step 1"}
{"op":"get","key":"a"}
{"op":"exists","key":"a"}
{"op":"search","query":"hello"}
{"op":"delete","key":"a"}' | bigmem batch
```

**Namespace isolation** for parallel agents or multi-project:
```bash
bigmem --namespace agent-1 put findings "..."
bigmem --namespace agent-2 put findings "..."
```

**Cleanup old facts** (pinned facts are always preserved):
```bash
bigmem cleanup --before 2025-01-01T00:00:00Z
bigmem cleanup --tags debug
```

**Export/import** for backups or transferring between databases:
```bash
bigmem export --file backup.ndjson
bigmem export --tags pin --file pinned.ndjson
bigmem --db new.db import --file backup.ndjson
```

## Tag conventions
- `pin` — survives cleanup (never auto-deleted)
- `decision` — architectural/design decisions
- `preference` — user preferences
- `debug` — debugging findings
- `context` — task/project context
- `blocker` — known issues

## Exit codes
- 0 = success, 1 = not found, 2 = usage error

## Development
```bash
uv sync
uv run pytest tests/
```
