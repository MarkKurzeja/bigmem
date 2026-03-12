"""Claude CLI runner for BigMem eval harness.

Invokes `claude --print --output-format stream-json` and parses the output
to extract the text response, tool calls, bigmem commands, and token usage.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class ClaudeResult:
  """Parsed result from a Claude CLI invocation."""

  text_response: str = ""
  tool_calls: list[dict] = field(default_factory=list)
  bigmem_commands: list[str] = field(default_factory=list)
  wall_time_seconds: float = 0.0
  input_tokens: int = 0
  output_tokens: int = 0
  cache_creation_tokens: int = 0
  cache_read_tokens: int = 0
  total_tokens: int = 0
  cost_usd: float = 0.0
  raw_events: list[dict] = field(default_factory=list)
  returncode: int = 0
  stderr: str = ""


def parse_stream_json(raw_output: str) -> ClaudeResult:
  """Parse stream-json output from Claude CLI into a ClaudeResult."""
  result = ClaudeResult()

  for line in raw_output.strip().split("\n"):
    line = line.strip()
    if not line:
      continue
    try:
      event = json.loads(line)
    except json.JSONDecodeError:
      continue

    result.raw_events.append(event)
    _process_event(event, result)

  # Total tokens = direct input + cached + output
  result.total_tokens = (
    result.input_tokens
    + result.cache_creation_tokens
    + result.cache_read_tokens
    + result.output_tokens
  )
  return result


def _process_event(event: dict, result: ClaudeResult) -> None:
  """Process a single stream-json event."""
  event_type = event.get("type")

  if event_type == "assistant":
    # Contains message with content blocks
    message = event.get("message", {})
    for block in message.get("content", []):
      if block.get("type") == "text":
        result.text_response += block.get("text", "")
      elif block.get("type") == "tool_use":
        tool = {
          "name": block.get("name", ""),
          "input": block.get("input", {}),
        }
        result.tool_calls.append(tool)
        # Extract bigmem commands from Bash tool calls
        if block.get("name") == "Bash":
          cmd = block.get("input", {}).get("command", "")
          if "bigmem" in cmd or "python -m bigmem" in cmd:
            result.bigmem_commands.append(cmd)

  elif event_type == "result":
    # Final event — authoritative source for token counts and cost
    result.cost_usd = event.get("total_cost_usd", 0.0)
    usage = event.get("usage", {})
    if usage:
      result.input_tokens = usage.get("input_tokens", 0)
      result.output_tokens = usage.get("output_tokens", 0)
      result.cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
      result.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    # modelUsage has per-model breakdown with full token counts
    model_usage = event.get("modelUsage", {})
    for model_info in model_usage.values():
      result.input_tokens = max(result.input_tokens, model_info.get("inputTokens", 0))
      result.output_tokens = max(result.output_tokens, model_info.get("outputTokens", 0))
      result.cache_creation_tokens = max(
        result.cache_creation_tokens,
        model_info.get("cacheCreationInputTokens", 0),
      )
      result.cache_read_tokens = max(
        result.cache_read_tokens, model_info.get("cacheReadInputTokens", 0)
      )


def run_claude(
  system_prompt: str,
  user_prompt: str,
  *,
  model: str = "sonnet",
  max_budget_usd: float = 0.50,
  timeout_seconds: int = 180,
) -> ClaudeResult:
  """Invoke Claude CLI in non-interactive mode and return parsed results.

  Args:
    system_prompt: System prompt with BigMem instructions.
    user_prompt: The question to ask.
    model: Model to use (default: sonnet).
    max_budget_usd: Maximum spend per invocation.
    timeout_seconds: Subprocess timeout.

  Returns:
    ClaudeResult with parsed response, tool calls, and token counts.
  """
  cmd = [
    "claude",
    "--print",
    "--verbose",
    "--output-format",
    "stream-json",
    "--model",
    model,
    "--max-budget-usd",
    str(max_budget_usd),
    "--no-session-persistence",
    "--dangerously-skip-permissions",
    "--system-prompt",
    system_prompt,
    user_prompt,
  ]

  # Remove CLAUDECODE env var to avoid nested session error
  env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

  start = time.monotonic()
  try:
    proc = subprocess.run(
      cmd,
      capture_output=True,
      text=True,
      timeout=timeout_seconds,
      env=env,
    )
  except subprocess.TimeoutExpired:
    result = ClaudeResult()
    result.stderr = f"Timed out after {timeout_seconds}s"
    result.returncode = -1
    result.wall_time_seconds = timeout_seconds
    return result

  elapsed = time.monotonic() - start

  result = parse_stream_json(proc.stdout)
  result.wall_time_seconds = elapsed
  result.returncode = proc.returncode
  result.stderr = proc.stderr
  return result
