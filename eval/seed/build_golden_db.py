"""Build golden databases for BigMem eval suite.

Parses alli_flash TOML decks and chapter summaries, generates NDJSON,
and pipes into `bigmem batch` for loading.

Usage:
  uv run python eval/seed/build_golden_db.py --tier baseline --output eval/golden/baseline.db
  uv run python eval/seed/build_golden_db.py --tier scale --output eval/golden/scale.db
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ALLI_FLASH_DIR = Path(__file__).resolve().parent.parent.parent.parent / "alli_flash"
DECKS_DIR = ALLI_FLASH_DIR / "decks"
SUMMARIES_DIR = ALLI_FLASH_DIR / "docs"

# Decks to sample from (skip example.toml)
DECK_FILES = [
  "mfm_part1_foundations.toml",
  "mfm_part2_physiology.toml",
  "mfm_part3a_imaging.toml",
  "mfm_part3b_fetal_disorders.toml",
  "mfm_part4_maternal_fetal.toml",
  "mfm_part5a_complications.toml",
  "mfm_part5b_complications.toml",
]

SUMMARY_FILES = [
  "chapter_summaries_ch1-7.md",
  "chapter_summaries_ch8-12.md",
  "chapter_summaries_ch13-20.md",
  "chapter_summaries_ch21-25.md",
  "chapter_summaries_ch26-31.md",
  "chapter_summaries_ch32-40.md",
  "chapter_summaries_ch41-50.md",
  "chapter_summaries_ch51-62.md",
  "chapter_summaries_ch63-73.md",
]

TIER_CARDS = {"baseline": 30, "scale": 100}
TIER_SUMMARIES = {"baseline": 20, "scale": 50}


def strip_html(text: str) -> str:
  """Strip HTML tags and convert to plain text."""
  text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
  text = re.sub(r"<[^>]+>", "", text)
  text = re.sub(r"&amp;", "&", text)
  text = re.sub(r"&lt;", "<", text)
  text = re.sub(r"&gt;", ">", text)
  text = re.sub(r"&nbsp;", " ", text)
  text = re.sub(r"&#\d+;", "", text)
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def slugify(text: str, max_len: int = 60) -> str:
  """Create a URL-safe slug from text."""
  text = text.lower()
  text = re.sub(r"[^a-z0-9\s-]", "", text)
  text = re.sub(r"[\s-]+", "-", text).strip("-")
  return text[:max_len].rstrip("-")


def parse_toml_deck(path: Path) -> list[dict]:
  """Parse a TOML deck file and return card dicts."""
  with open(path, "rb") as f:
    data = tomllib.load(f)
  return data.get("cards", [])


def extract_cards(tier: str) -> list[dict]:
  """Extract flashcard facts from alli_flash TOML decks.

  Returns list of batch operations (NDJSON-ready dicts).
  """
  target_count = TIER_CARDS[tier]
  per_deck = max(1, target_count // len(DECK_FILES))
  ops = []

  for deck_file in DECK_FILES:
    path = DECKS_DIR / deck_file
    if not path.exists():
      print(f"Warning: {path} not found, skipping", file=sys.stderr)
      continue

    cards = parse_toml_deck(path)
    # Prefer high_yield cards, then take any basic cards
    high_yield = [c for c in cards if "high_yield" in c.get("tags", []) and c.get("model") == "basic"]
    basic = [c for c in cards if c.get("model") == "basic"]

    pool = high_yield if len(high_yield) >= per_deck else basic
    selected = pool[:per_deck]

    deck_slug = deck_file.replace(".toml", "").replace("mfm_", "")
    for i, card in enumerate(selected):
      front = card.get("front", "")
      back = card.get("back", "")
      tags = card.get("tags", [])

      key = f"{deck_slug}-{slugify(front[:80])}"
      value = json.dumps({
        "question": front,
        "answer": strip_html(back),
        "source_tags": tags,
      })
      tag_str = ",".join(tags) if tags else ""

      ops.append({
        "op": "put",
        "key": key,
        "value": value,
        "tags": tag_str,
        "namespace": "medical-facts",
      })

  return ops[:target_count]


def extract_summaries(tier: str) -> list[dict]:
  """Extract chapter summary facts from markdown files.

  Parses section headers and bullet points into individual facts.
  """
  target_count = TIER_SUMMARIES[tier]
  ops = []

  for summary_file in SUMMARY_FILES:
    path = SUMMARIES_DIR / summary_file
    if not path.exists():
      continue

    text = path.read_text()
    # Parse chapter sections: ## Chapter N: Title
    chapters = re.split(r"^## (Chapter \d+:.+)$", text, flags=re.MULTILINE)

    for i in range(1, len(chapters), 2):
      header = chapters[i].strip()
      body = chapters[i + 1] if i + 1 < len(chapters) else ""

      # Extract chapter number
      ch_match = re.match(r"Chapter (\d+):", header)
      if not ch_match:
        continue
      ch_num = ch_match.group(1)

      # Split into subsections by ### headers
      subsections = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
      for j in range(1, len(subsections), 2):
        sub_header = subsections[j].strip()
        sub_body = subsections[j + 1] if j + 1 < len(subsections) else ""
        sub_body = sub_body.strip()

        if len(sub_body) < 50:
          continue

        key = f"summary-ch{ch_num}-{slugify(sub_header)}"
        value = json.dumps({
          "chapter": int(ch_num),
          "section": sub_header,
          "content": sub_body[:2000],
        })

        ops.append({
          "op": "put",
          "key": key,
          "value": value,
          "tags": f"summary,ch{ch_num}",
          "namespace": "medical-facts",
        })

      if len(ops) >= target_count:
        break
    if len(ops) >= target_count:
      break

  return ops[:target_count]


def load_via_batch(ops: list[dict], db_path: str) -> None:
  """Load facts into BigMem using the batch command."""
  ndjson = "\n".join(json.dumps(op) for op in ops)

  bigmem_root = Path(__file__).resolve().parent.parent.parent
  result = subprocess.run(
    [sys.executable, "-m", "bigmem", "--db", db_path, "batch"],
    input=ndjson,
    capture_output=True,
    text=True,
    cwd=str(bigmem_root),
  )

  if result.returncode != 0:
    print(f"Batch load failed: {result.stderr}", file=sys.stderr)
    sys.exit(1)

  # Count successes/failures
  successes = 0
  failures = 0
  for line in result.stdout.strip().split("\n"):
    if not line:
      continue
    resp = json.loads(line)
    if resp.get("ok"):
      successes += 1
    else:
      failures += 1
      print(f"  Failed: {resp}", file=sys.stderr)

  print(f"Loaded {successes} facts ({failures} failures)")


def verify_db(db_path: str) -> None:
  """Run bigmem stats on the DB to verify."""
  bigmem_root = Path(__file__).resolve().parent.parent.parent
  result = subprocess.run(
    [sys.executable, "-m", "bigmem", "--db", db_path, "--pretty", "stats"],
    capture_output=True,
    text=True,
    cwd=str(bigmem_root),
  )
  print(result.stdout)


def main():
  parser = argparse.ArgumentParser(description="Build golden BigMem database for eval")
  parser.add_argument("--tier", choices=["baseline", "scale"], required=True)
  parser.add_argument("--output", required=True, help="Output database path")
  args = parser.parse_args()

  db_path = os.path.abspath(args.output)

  # Remove existing DB if present
  for suffix in ["", "-wal", "-shm"]:
    p = db_path + suffix
    if os.path.exists(p):
      os.remove(p)

  print(f"Building {args.tier} golden DB at {db_path}")
  print(f"  Target: {TIER_CARDS[args.tier]} cards + {TIER_SUMMARIES[args.tier]} summaries")

  # Extract data
  card_ops = extract_cards(args.tier)
  print(f"  Extracted {len(card_ops)} card facts")

  summary_ops = extract_summaries(args.tier)
  print(f"  Extracted {len(summary_ops)} summary facts")

  all_ops = card_ops + summary_ops
  print(f"  Total: {len(all_ops)} facts")

  # Load into DB
  load_via_batch(all_ops, db_path)

  # Verify
  print("\nDatabase stats:")
  verify_db(db_path)


if __name__ == "__main__":
  main()
