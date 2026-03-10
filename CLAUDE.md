# bigmem — SQLite-backed memory store for AI agents

## Quick Reference

```bash
# Store a fact (auto-wraps plain strings as JSON)
bigmem put <key> <value> [--tags t1,t2] [--source agent-id] [--session sid] [--ephemeral] [-q]

# Retrieve facts (single or multi-key)
bigmem get <key>              # full fact JSON
bigmem get <key> --raw        # just the value, for piping
bigmem get <k1> <k2> <k3>    # returns array, null for missing keys

# Search and list
bigmem search <query>         # FTS5 full-text search
bigmem list [--tags t] [--keys-only] [--session s] [--ephemeral] [--persistent]

# Delete
bigmem delete <key>
bigmem session-end <session-id>   # delete all ephemeral facts for a session

# Batch (NDJSON on stdin, one result per line)
echo '{"op":"put","key":"k","value":"v"}
{"op":"get","key":"k"}
{"op":"delete","key":"k"}' | bigmem batch

# Stats
bigmem stats
```

## Global flags
- `--db PATH` — database file (default: `~/.bigmem.db`). Use separate paths for parallel agents.
- `--namespace NS` — isolate facts by namespace (default: `default`)
- `--pretty` — pretty-print JSON (default: compact for token efficiency)

## Agent patterns

**Store structured data:**
```bash
bigmem put user_prefs '{"theme":"dark","lang":"en"}' --tags config
```

**Quick silent writes (no output, saves tokens):**
```bash
bigmem put status "running task 3" -q
```

**Read-modify-write:**
```bash
VALUE=$(bigmem get config --raw)
# ... modify VALUE ...
bigmem put config "$VALUE" -q
```

**Fetch multiple keys at once:**
```bash
bigmem get user_name user_role user_prefs
```

**Ephemeral session memory (auto-cleaned):**
```bash
bigmem put scratch "temp data" --ephemeral --session $SESSION_ID
# ... later ...
bigmem session-end $SESSION_ID
```

**Pipe content in:**
```bash
cat results.json | bigmem put analysis_results --stdin
```

## Exit codes
- 0 = success
- 1 = not found
- 2 = usage error

## Development
```bash
uv sync
uv run pytest tests/
```
