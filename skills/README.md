# bigmem Skills

Claude Code skills for using bigmem as a persistent memory store. Import these into your project to give Claude agents the ability to remember and recall facts across sessions.

## Available Skills

| Skill | Description |
|-------|-------------|
| `bigmem` | Full access to the memory store — bulk operations, batch queries, stats, session cleanup, and all CLI commands |
| `remember` | Store a fact silently (runs with `-q` to avoid context noise) |
| `recall` | Retrieve a fact by key, search query, or tag |

## Setup

Copy the skill folders into your project's `.claude/skills/` directory:

```bash
cp -r skills/bigmem  /path/to/your/project/.claude/skills/
cp -r skills/recall   /path/to/your/project/.claude/skills/
cp -r skills/remember /path/to/your/project/.claude/skills/
```

Requires `bigmem` to be installed and available on `PATH` (`uv tool install bigmem` or `pip install bigmem`).
