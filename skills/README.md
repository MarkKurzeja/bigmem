# bigmem Skills

Claude Code skill for using bigmem as a persistent memory store. Import into your project to give Claude agents the ability to store, retrieve, and search facts across sessions.

## Setup

Copy the skill folder into your project's `.claude/skills/` directory:

```bash
cp -r skills/bigmem /path/to/your/project/.claude/skills/
```

Requires `bigmem` to be installed and available on `PATH` (`uv tool install bigmem` or `pip install bigmem`).
