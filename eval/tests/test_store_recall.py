"""Store-then-recall eval: test the full remember → retrieve loop.

Has Claude store 3 facts via bigmem put, then in a separate invocation
asks it to retrieve them. Tests that facts survive the round-trip and
are findable via search.

Usage:
  uv run pytest eval/tests/test_store_recall.py -v -s
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from eval.harness.claude_runner import run_claude

BIGMEM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Facts to store — diverse content to test key generation and retrieval
FACTS_TO_STORE = [
  {
    "key": "project-stack",
    "value": "React frontend with FastAPI backend, deployed on AWS ECS",
    "tags": "decision,pin",
  },
  {
    "key": "debug-auth-bug",
    "value": "JWT token refresh race condition: two concurrent requests both see expired token, both try refresh, second one fails because first already rotated the refresh token",
    "tags": "debug,blocker",
  },
  {
    "key": "user-pref-testing",
    "value": "User prefers pytest over unittest, always run with -v flag, use fixtures not setup/teardown",
    "tags": "preference",
  },
]

# Questions to test retrieval — each targets a stored fact
RECALL_QUESTIONS = [
  {
    "id": "r001",
    "query": "What is our project tech stack?",
    "expected_key": "project-stack",
    "expected_terms": ["React", "FastAPI", "AWS"],
  },
  {
    "id": "r002",
    "query": "What was the authentication bug we found?",
    "expected_key": "debug-auth-bug",
    "expected_terms": ["JWT", "refresh", "race condition"],
  },
  {
    "id": "r003",
    "query": "What are the user's testing preferences?",
    "expected_key": "user-pref-testing",
    "expected_terms": ["pytest", "fixtures"],
  },
]


def _store_prompt(db_path: str) -> str:
  return f"""\
You have access to a persistent memory store called BigMem via the command line.
The database is located at: {db_path}

Store facts using: python -m bigmem --db {db_path} put <key> '<value>' --tags tag1,tag2 -q

Store ALL of the following facts. Use the exact keys and values provided.
Do NOT search or read — just store them.
After storing all facts, respond with "Done."
"""


def _recall_prompt(db_path: str) -> str:
  return f"""\
You have access to a persistent memory store called BigMem via the command line.
The database is located at: {db_path}

Commands:
- `python -m bigmem --db {db_path} search "<query>"` — Full-text search (use 1-3 keywords)
- `python -m bigmem --db {db_path} get <key> --raw` — Get by exact key
- `python -m bigmem --db {db_path} list --keys-only` — List all available keys

Strategy: Start with `list --keys-only` to see what's available, then use `get <key> --raw` for the most relevant key. Use `search` if you need to find facts by content.

Rules:
1. ALWAYS check BigMem before answering.
2. Only use information from BigMem — do NOT use training data.
3. Cite the BigMem key(s) you used.
4. If not found, say "Not found in memory store."

Format your response as:
**Answer:** [answer from BigMem]
**Source:** [bigmem key]
"""


class TestStoreRecall:
  """Test the full store → recall loop."""

  def test_store_then_recall(self, tmp_path, eval_model):
    """Store 3 facts, then recall each one in a separate Claude invocation."""
    db_path = str(tmp_path / "store_recall.db")

    # Phase 1: Store facts
    store_instructions = "\n".join(
      f"- Key: `{f['key']}`, Value: `{f['value']}`, Tags: `{f['tags']}`" for f in FACTS_TO_STORE
    )
    store_result = run_claude(
      _store_prompt(db_path),
      f"Store these facts:\n{store_instructions}",
      model=eval_model,
      max_budget_usd=0.10,
    )
    print(f"\n=== STORE PHASE ===")
    print(f"  Commands: {len(store_result.bigmem_commands)}")
    print(f"  Cost: ${store_result.cost_usd:.4f}")
    print(f"  Wall time: {store_result.wall_time_seconds:.1f}s")

    # Verify facts were actually stored
    for fact in FACTS_TO_STORE:
      result = subprocess.run(
        [
          sys.executable,
          "-m",
          "bigmem",
          "--db",
          db_path,
          "exists",
          fact["key"],
        ],
        capture_output=True,
        text=True,
        cwd=BIGMEM_ROOT,
      )
      assert result.returncode == 0, f"Fact '{fact['key']}' was not stored"
    print(f"  All {len(FACTS_TO_STORE)} facts verified in DB")

    # Phase 2: Recall each fact
    recall_system = _recall_prompt(db_path)
    recall_results = []

    for q in RECALL_QUESTIONS:
      print(f"\n--- {q['id']}: {q['query']} ---")
      result = run_claude(
        recall_system,
        q["query"],
        model=eval_model,
        max_budget_usd=0.10,
      )
      print(f"  Commands: {len(result.bigmem_commands)}")
      print(f"  Cost: ${result.cost_usd:.4f}")
      print(f"  Wall time: {result.wall_time_seconds:.1f}s")

      # Check if expected terms appear in response
      response_lower = result.text_response.lower()
      found_terms = [t for t in q["expected_terms"] if t.lower() in response_lower]
      missing_terms = [t for t in q["expected_terms"] if t.lower() not in response_lower]
      accuracy = len(found_terms) / len(q["expected_terms"])

      # Check if the expected key was cited
      key_cited = q["expected_key"] in result.text_response

      print(f"  Accuracy: {accuracy:.2f} ({len(found_terms)}/{len(q['expected_terms'])} terms)")
      print(f"  Key cited: {key_cited}")
      if missing_terms:
        print(f"  Missing: {missing_terms}")

      recall_results.append(
        {
          "id": q["id"],
          "accuracy": accuracy,
          "key_cited": key_cited,
          "cost": result.cost_usd,
          "wall_time": result.wall_time_seconds,
        }
      )

    # Assertions
    avg_accuracy = sum(r["accuracy"] for r in recall_results) / len(recall_results)
    keys_cited = sum(1 for r in recall_results if r["key_cited"])
    total_cost = store_result.cost_usd + sum(r["cost"] for r in recall_results)

    print(f"\n=== SUMMARY ===")
    print(f"  Avg accuracy: {avg_accuracy:.2f}")
    print(f"  Keys cited: {keys_cited}/{len(recall_results)}")
    print(f"  Total cost: ${total_cost:.4f}")

    assert avg_accuracy > 0.5, f"Average recall accuracy too low: {avg_accuracy:.2f}"
    assert keys_cited >= 2, f"Too few keys cited: {keys_cited}/{len(recall_results)}"
