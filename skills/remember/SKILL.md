---
name: remember
description: Store a fact for later recall. Use when you learn something important that should persist across sessions — decisions, preferences, architecture notes, debugging findings, or task context. Runs silently to avoid context pollution.
allowed-tools: Bash
context: fork
argument-hint: "<key> <value> [--tags t1,t2] [--source agent-id]"
---

# Store a fact in bigmem

Store the provided information using bigmem. Run silently to avoid polluting the parent context.

```bash
bigmem put $ARGUMENTS -q
```

If `$ARGUMENTS` is empty or unclear, ask the user what to remember.

If the value contains complex or multi-line content, use `--stdin`:
```bash
echo '<value>' | bigmem put <key> --stdin -q
```

After storing, respond with only a brief confirmation like: "Remembered `<key>`."

Common tag conventions:
- `decision` — architectural or design decisions
- `preference` — user preferences
- `debug` — debugging findings
- `context` — task/project context
- `blocker` — known issues or blockers
