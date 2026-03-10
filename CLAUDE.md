# bigmem — SQLite-backed memory store for AI agents

## Skills

Use these slash commands instead of calling bigmem directly — they run in forked context to avoid polluting the conversation:

- `/remember <key> <value>` — store a fact silently
- `/recall <key-or-query>` — retrieve facts or search
- `/bigmem <command>` — full CLI access (batch, stats, cleanup)

## Quick CLI Reference

```bash
bigmem put <key> <value> [--tags t1,t2] [--source agent-id] [-q]
bigmem get <key> [key2...] [--raw]
bigmem search <query> [--tags t]
bigmem list [--tags t] [--keys-only] [--session s]
bigmem delete <key>
bigmem session-end <session-id>
echo '{"op":"put","key":"k","value":"v"}' | bigmem batch
bigmem stats
```

## Global flags
- `--db PATH` — database file (default: `~/.bigmem.db`). Use separate paths for parallel agents.
- `--namespace NS` — isolate facts by namespace (default: `default`)
- `--pretty` — pretty-print JSON (default: compact for token efficiency)

## Context management patterns

**Pin critical facts** so they survive context compaction:
```bash
bigmem put project_arch "monorepo, React frontend, FastAPI backend" --tags pin
```
Pinned facts are automatically re-injected after compaction via SessionStart hook.

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

**Ephemeral session memory** for scratch data that auto-cleans:
```bash
bigmem put scratch "temp" --ephemeral --session $SESSION_ID
bigmem session-end $SESSION_ID
```

**Batch operations** for bulk work (NDJSON on stdin):
```bash
echo '{"op":"put","key":"a","value":"1"}
{"op":"get","key":"a"}' | bigmem batch
```

**Namespace isolation** for parallel agents or multi-project:
```bash
bigmem --namespace agent-1 put findings "..."
bigmem --namespace agent-2 put findings "..."
```

## Tag conventions
- `pin` — survives compaction (auto-re-injected)
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
