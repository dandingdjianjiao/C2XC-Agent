from __future__ import annotations

from enum import Enum


class RecapState(Enum):
    """Minimal ReCAP state machine (matches ReCAP-1 repo style)."""

    DOWN = "down"
    ACTION_TAKEN = "action_taken"
    UP = "up"

