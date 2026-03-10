#!/bin/bash
# Re-inject important memories after context compaction or session resume.
# Called by SessionStart hook on compact/resume events.
# Only outputs facts tagged "pin" — these survive compaction.

DB="${BIGMEM_DB:-$HOME/.bigmem.db}"

if [ ! -f "$DB" ]; then
    exit 0
fi

PINNED=$(bigmem --db "$DB" list --tags pin --keys-only 2>/dev/null)
if [ -z "$PINNED" ] || [ "$PINNED" = "[]" ]; then
    exit 0
fi

echo "## Restored memories from bigmem (pinned facts)"
echo ""
bigmem --db "$DB" list --tags pin --pretty 2>/dev/null
echo ""
echo "Use /recall to retrieve other stored facts. Use /remember to store new ones."
