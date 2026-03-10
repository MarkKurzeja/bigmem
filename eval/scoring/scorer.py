"""Scoring module for BigMem eval responses.

Scores Claude's responses against ground truth on a balanced scorecard:
accuracy, completeness, hallucination-free, citation quality, token/tool efficiency.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class QuestionScore:
  """Score for a single question."""

  question_id: str
  category: str
  topic: str
  accuracy: float = 0.0
  completeness: float = 0.0
  hallucination_free: float = 1.0
  citation_quality: float = 0.0
  bigmem_commands: int = 0
  input_tokens: int = 0
  output_tokens: int = 0
  cache_creation_tokens: int = 0
  cache_read_tokens: int = 0
  total_tokens: int = 0
  cost_usd: float = 0.0
  wall_time: float = 0.0
  error: str = ""


def parse_response_sections(text: str) -> dict[str, str]:
  """Parse Claude's structured response into sections.

  Expects format:
    **Answer:** ...
    **Sources:** ...
    **Confidence:** ...
  """
  sections: dict[str, str] = {}
  for key in ("Answer", "Sources", "Confidence"):
    pattern = rf"\*\*{key}:\*\*\s*(.*?)(?=\*\*\w+:\*\*|$)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
      sections[key.lower()] = match.group(1).strip()
  return sections


def extract_cited_keys(sources_text: str) -> list[str]:
  """Extract BigMem keys from the Sources section."""
  if not sources_text:
    return []
  # Prefer backtick-wrapped keys first (most reliable)
  keys = re.findall(r"`([a-z0-9][a-z0-9_-]{5,})`", sources_text)
  if keys:
    return keys
  # Fallback: long slugified strings (min 20 chars to avoid false positives)
  keys = re.findall(r"\b([a-z0-9][a-z0-9_-]{20,})\b", sources_text)
  return keys


def key_exists_in_db(key: str, db_path: str, namespace: str = "medical-facts") -> bool:
  """Check if a key exists in the BigMem database."""
  result = subprocess.run(
    [sys.executable, "-m", "bigmem", "--db", db_path, "--namespace", namespace, "exists", key],
    capture_output=True,
    text=True,
    cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent),
  )
  return result.returncode == 0


def score_accuracy(response_text: str, expected_answer: str, key_terms: list[str]) -> float:
  """Score accuracy based on key term overlap.

  Returns fraction of key_terms found in the response. Uses the full response
  text (not just the parsed Answer section) to be robust against formatting
  variations.
  """
  if not key_terms:
    # For negative questions, check if Claude correctly said "not found"
    not_found_phrases = ["not found", "no results", "no information", "does not contain", "couldn't find", "could not find", "no relevant"]
    response_lower = response_text.lower()
    for phrase in not_found_phrases:
      if phrase in response_lower:
        return 1.0
    return 0.0

  # Normalize whitespace for matching (e.g., "25mm" matches "25 mm")
  response_normalized = re.sub(r"\s+", " ", response_text.lower())
  response_nospace = re.sub(r"\s+", "", response_text.lower())
  found = 0
  for term in key_terms:
    term_lower = term.lower()
    term_nospace = re.sub(r"\s+", "", term_lower)
    if term_lower in response_normalized or term_nospace in response_nospace:
      found += 1
  return found / len(key_terms)


def score_completeness(cited_keys: list[str], relevant_keys: list[str]) -> float:
  """Score what fraction of relevant keys were cited."""
  if not relevant_keys:
    return 1.0  # No keys expected (negative question)
  found = sum(1 for k in relevant_keys if any(k in cited for cited in cited_keys))
  return found / len(relevant_keys)


def score_hallucination(
  response_text: str,
  cited_keys: list[str],
  db_path: str,
  category: str,
) -> float:
  """Score hallucination resistance.

  Returns 1.0 if no hallucination, 0.0 if hallucinated.
  """
  if category == "negative":
    not_found_phrases = ["not found", "no results", "no information", "does not contain"]
    response_lower = response_text.lower()
    for phrase in not_found_phrases:
      if phrase in response_lower:
        return 1.0
    return 0.0

  # Check if cited keys actually exist in the DB
  if not cited_keys:
    return 0.5  # No citations at all is ambiguous

  for key in cited_keys:
    if not key_exists_in_db(key, db_path):
      return 0.0  # Cited a nonexistent key

  return 1.0


def score_citation_quality(cited_keys: list[str], db_path: str) -> float:
  """Score fraction of cited keys that actually exist in the DB."""
  if not cited_keys:
    return 0.0
  valid = sum(1 for k in cited_keys if key_exists_in_db(k, db_path))
  return valid / len(cited_keys)


def score_response(
  question: dict,
  text_response: str,
  bigmem_commands: list[str],
  input_tokens: int,
  output_tokens: int,
  wall_time: float,
  db_path: str,
  cache_creation_tokens: int = 0,
  cache_read_tokens: int = 0,
  cost_usd: float = 0.0,
) -> QuestionScore:
  """Score a single response against ground truth.

  Args:
    question: Ground truth question dict from ground_truth.json.
    text_response: Claude's full text response.
    bigmem_commands: List of bigmem CLI commands Claude ran.
    input_tokens: Input token count.
    output_tokens: Output token count.
    wall_time: Wall-clock seconds.
    db_path: Path to the test database.

  Returns:
    QuestionScore with all metrics filled in.
  """
  total = input_tokens + cache_creation_tokens + cache_read_tokens + output_tokens
  score = QuestionScore(
    question_id=question["id"],
    category=question["category"],
    topic=question["topic"],
    bigmem_commands=len(bigmem_commands),
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cache_creation_tokens=cache_creation_tokens,
    cache_read_tokens=cache_read_tokens,
    total_tokens=total,
    cost_usd=cost_usd,
    wall_time=wall_time,
  )

  sections = parse_response_sections(text_response)
  sources_text = sections.get("sources", "")
  cited_keys = extract_cited_keys(sources_text)

  # Use full text_response for accuracy to be robust against parsing issues
  score.accuracy = score_accuracy(
    text_response,
    question["expected_answer"],
    question.get("key_terms", []),
  )

  score.completeness = score_completeness(
    cited_keys,
    question.get("relevant_keys", []),
  )

  score.hallucination_free = score_hallucination(
    text_response,
    cited_keys,
    db_path,
    question["category"],
  )

  if question["category"] != "negative":
    score.citation_quality = score_citation_quality(cited_keys, db_path)
  else:
    score.citation_quality = 1.0  # N/A for negative questions

  return score
