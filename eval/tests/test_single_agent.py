"""Single-agent eval: test Claude's ability to use BigMem for Q&A retrieval.

Runs 10 questions against a baseline golden DB (~50 facts) and scores
responses on accuracy, completeness, hallucination resistance, and efficiency.

Usage:
  uv run pytest eval/tests/test_single_agent.py -v -s
  uv run pytest eval/tests/test_single_agent.py -v -s --eval-model opus
"""

from __future__ import annotations

import pytest

from eval.harness.claude_runner import run_claude
from eval.harness.prompt_templates import build_system_prompt, build_user_prompt
from eval.scoring.report import generate_report
from eval.scoring.scorer import QuestionScore, score_response


class TestSingleAgent:
  """Run all ground truth questions against Claude with BigMem."""

  def test_eval_all_questions(
    self, baseline_db, ground_truth, eval_model, max_budget, reports_dir
  ):
    """Run the full eval suite and generate a report."""
    questions = ground_truth["questions"]
    system_prompt = build_system_prompt(baseline_db)
    scores: list[QuestionScore] = []

    for q in questions:
      print(f"\n--- {q['id']}: {q['question'][:60]}... ---")

      user_prompt = build_user_prompt(q["question"])
      result = run_claude(
        system_prompt,
        user_prompt,
        model=eval_model,
        max_budget_usd=max_budget,
      )

      if result.returncode != 0 and not result.text_response:
        print(f"  ERROR: rc={result.returncode}, stderr={result.stderr[:200]}")
        s = QuestionScore(
          question_id=q["id"],
          category=q["category"],
          topic=q["topic"],
          error=f"Claude returned rc={result.returncode}: {result.stderr[:200]}",
        )
        scores.append(s)
        continue

      print(f"  Tokens: {result.input_tokens} in + {result.output_tokens} out"
            f" (cache: {result.cache_creation_tokens} create, {result.cache_read_tokens} read)"
            f" = {result.total_tokens} total")
      print(f"  Cost: ${result.cost_usd:.4f}")
      print(f"  BigMem commands: {len(result.bigmem_commands)}")
      print(f"  Wall time: {result.wall_time_seconds:.1f}s")

      s = score_response(
        question=q,
        text_response=result.text_response,
        bigmem_commands=result.bigmem_commands,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        wall_time=result.wall_time_seconds,
        db_path=baseline_db,
        cache_creation_tokens=result.cache_creation_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cost_usd=result.cost_usd,
      )
      scores.append(s)

      print(f"  Accuracy: {s.accuracy:.2f}")
      print(f"  Completeness: {s.completeness:.2f}")
      print(f"  Hallucination-free: {s.hallucination_free:.2f}")
      print(f"  Citation quality: {s.citation_quality:.2f}")

    # Generate report
    report = generate_report(
      scores,
      model=eval_model,
      tier="baseline",
      total_facts=48,
      output_dir=reports_dir,
    )
    print("\n" + report)

    # Basic assertions: at least some questions should score well
    avg_accuracy = sum(s.accuracy for s in scores) / len(scores)
    avg_halluc = sum(s.hallucination_free for s in scores) / len(scores)

    # These thresholds are intentionally lenient for initial runs
    assert avg_accuracy > 0.3, f"Average accuracy too low: {avg_accuracy:.2f}"
    assert avg_halluc > 0.3, f"Average hallucination-free too low: {avg_halluc:.2f}"
