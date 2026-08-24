from typing import Any

from pydantic import BaseModel


class Step(BaseModel):
    """
    One agent-proposed action, not yet executed — the tool hasn't run and no
    observation exists for it yet. The caller inspects (and can log, stream,
    or veto) `tool_name`/`tool_args`, optionally edits `trajectory` (e.g. to
    correct an earlier observation, or roll it back), and then calls
    `resume(step, ...)` to actually run the tool and advance to whatever the
    agent proposes next.

    Built from plain, serializable data (a dict and an int) rather than a
    live suspended frame — the way a Python generator would hold one — so a
    `Step` can be persisted, handed to a different process, and resumed
    arbitrarily later.
    """

    model_config = {"arbitrary_types_allowed": True}

    trajectory: dict[str, Any]
    idx: int
    thought: str
    tool_name: str
    tool_args: dict[str, Any]
