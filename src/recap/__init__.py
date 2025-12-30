"""ReCAP-style recursive planning/execution engine.

This package implements the core ReCAP loop from the paper:
  ReCAP: Recursive Context-Aware Reasoning and Planning for LLM Agents

We intentionally keep it lightweight (no external orchestration framework),
and adapt primitive actions to this repo's domain (kb_search / generate_recipes).
"""

