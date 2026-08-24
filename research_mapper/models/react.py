from typing import Any

from pydantic import BaseModel


class Suspended(BaseModel):
    """
    Returned instead of a `dspy.Prediction` when the loop reaches a tool
    named in `suspend_on` — the tool is *not* called. The caller is expected
    to persist `trajectory` and `idx`, obtain an answer for `tool_name`/
    `tool_args` out of band (e.g. from a human, on a different process, after
    an arbitrary delay), and later call `resume()` with it.
    """

    model_config = {"arbitrary_types_allowed": True}

    trajectory: dict[str, Any]
    idx: int
    tool_name: str
    tool_args: dict[str, Any]
