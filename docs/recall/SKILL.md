---
name: recall
description: Retrieve stored facts from memory. Use when you need to check what was previously learned, look up a decision, find a preference, or search for context from earlier sessions.
allowed-tools: Bash
context: fork
argument-hint: "<key-or-search-query>"
---

# Retrieve facts from bigmem

Retrieve stored information. Determine the best retrieval strategy from the arguments:

**If the argument looks like an exact key** (no spaces, looks like an identifier):
```bash
bigmem get $ARGUMENTS
```

**If the argument looks like a search query** (has spaces, is a question, is descriptive):
```bash
bigmem search "$ARGUMENTS"
```

**If the argument is a tag** (prefixed with `#` or `tag:`):
```bash
bigmem list --tags <tag-name>
```

**If no argument given**, show what's available:
```bash
bigmem list --keys-only
```

Return the results clearly and concisely. For single facts, just state the value. For multiple results, use a brief list format. Do not include metadata (timestamps, namespace) unless the user asks for it.
