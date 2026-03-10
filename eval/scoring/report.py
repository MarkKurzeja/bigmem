"""Generate markdown eval reports from scored results."""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from pathlib import Path

from eval.scoring.scorer import QuestionScore


def generate_report(
  scores: list[QuestionScore],
  *,
  model: str = "sonnet",
  tier: str = "baseline",
  total_facts: int = 0,
  output_dir: str | None = None,
) -> str:
  """Generate a markdown report from scored results.

  Args:
    scores: List of QuestionScore objects.
    model: Model used for the eval.
    tier: Data tier (baseline/scale).
    total_facts: Number of facts in the golden DB.
    output_dir: If provided, write report to this directory.

  Returns:
    Markdown report string.
  """
  now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

  def _stats(values: list[float]) -> dict:
    if not values:
      return {"mean": 0, "min": 0, "max": 0, "stdev": 0}
    return {
      "mean": statistics.mean(values),
      "min": min(values),
      "max": max(values),
      "stdev": statistics.stdev(values) if len(values) > 1 else 0,
    }

  acc = _stats([s.accuracy for s in scores])
  comp = _stats([s.completeness for s in scores])
  hall = _stats([s.hallucination_free for s in scores])
  cite = _stats([s.citation_quality for s in scores])
  cmds = _stats([float(s.bigmem_commands) for s in scores])
  tok = _stats([float(s.total_tokens) for s in scores])
  wall = _stats([s.wall_time for s in scores])

  total_tok = sum(s.total_tokens for s in scores)
  total_in = sum(s.input_tokens for s in scores)
  total_out = sum(s.output_tokens for s in scores)
  total_cache_create = sum(s.cache_creation_tokens for s in scores)
  total_cache_read = sum(s.cache_read_tokens for s in scores)
  total_cost = sum(s.cost_usd for s in scores)
  total_wall = sum(s.wall_time for s in scores)

  lines = [
    f"# BigMem Eval Report",
    f"**Date:** {now}",
    f"**Model:** {model}",
    f"**Tier:** {tier} ({total_facts} facts seeded)",
    f"**Questions:** {len(scores)}",
    "",
    "## Aggregate Scores",
    "",
    "| Metric | Mean | Min | Max | Stdev |",
    "|--------|------|-----|-----|-------|",
    f"| Accuracy | {acc['mean']:.2f} | {acc['min']:.2f} | {acc['max']:.2f} | {acc['stdev']:.2f} |",
    f"| Completeness | {comp['mean']:.2f} | {comp['min']:.2f} | {comp['max']:.2f} | {comp['stdev']:.2f} |",
    f"| Hallucination-free | {hall['mean']:.2f} | {hall['min']:.2f} | {hall['max']:.2f} | {hall['stdev']:.2f} |",
    f"| Citation quality | {cite['mean']:.2f} | {cite['min']:.2f} | {cite['max']:.2f} | {cite['stdev']:.2f} |",
    f"| BigMem commands | {cmds['mean']:.1f} | {cmds['min']:.0f} | {cmds['max']:.0f} | {cmds['stdev']:.1f} |",
    f"| Total tokens | {tok['mean']:.0f} | {tok['min']:.0f} | {tok['max']:.0f} | {tok['stdev']:.0f} |",
    f"| Wall time (s) | {wall['mean']:.1f} | {wall['min']:.1f} | {wall['max']:.1f} | {wall['stdev']:.1f} |",
    "",
    "## Totals",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Total input tokens | {total_in:,} |",
    f"| Total output tokens | {total_out:,} |",
    f"| Cache creation tokens | {total_cache_create:,} |",
    f"| Cache read tokens | {total_cache_read:,} |",
    f"| Total tokens | {total_tok:,} |",
    f"| Total cost (USD) | ${total_cost:.4f} |",
    f"| Total wall time | {total_wall:.1f}s |",
    "",
    "## Per-Question Detail",
    "",
    "| ID | Category | Topic | Accuracy | Complete | Halluc | Citation | Cmds | Tokens | Time |",
    "|----|----------|-------|----------|----------|--------|----------|------|--------|------|",
  ]

  for s in scores:
    lines.append(
      f"| {s.question_id} | {s.category} | {s.topic} "
      f"| {s.accuracy:.2f} | {s.completeness:.2f} | {s.hallucination_free:.2f} "
      f"| {s.citation_quality:.2f} | {s.bigmem_commands} | {s.total_tokens:,} | {s.wall_time:.1f}s |"
    )

  # Errors section
  errors = [s for s in scores if s.error]
  if errors:
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    for s in errors:
      lines.append(f"- **{s.question_id}:** {s.error}")

  report = "\n".join(lines) + "\n"

  if output_dir:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(output_dir) / f"run_{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"Report written to {out_path}")

  return report
