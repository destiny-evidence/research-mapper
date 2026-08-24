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

    def with_observation(self, observation: Any) -> "Step":
        """
        Returns a copy of this Step with `observation` already supplied for its own
        not-yet-executed tool call, resume() sees it and uses it instead of actually
        calling the tool. This is how a caller answers on a tool's behalf (e.g. a
        clarifying question only a human can answer) without the tool itself needing
        any caller-specific state or wiring.
        """
        return self.model_copy(
            update={
                "trajectory": {
                    **self.trajectory,
                    f"observation_{self.idx}": observation,
                }
            }
        )
