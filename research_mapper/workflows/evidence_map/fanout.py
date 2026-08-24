"""Glue for driving dspy fan-outs from a step."""

import threading
from typing import Any

import dspy

from research_mapper.engine.context import StepContext

NO_STRAGGLER_RESUBMISSION = 0

MAX_CONCURRENCY = 8


class _Tracked(dspy.Module):
    def __init__(self, inner: dspy.Module, ctx: StepContext, total: int, note: str):
        self._inner = inner
        self._ctx = ctx
        self._total = total
        self._note = note
        self._done = 0
        self._failed = 0
        self._lock = threading.Lock()

    def forward(self, **inputs: Any) -> dspy.Prediction:
        """Run one item and report it, re-raising so dspy still records the failure."""
        try:
            prediction = self._inner(**inputs)
        except Exception:
            self._report(failed=True)
            raise
        self._report(failed=False)
        return prediction

    def _report(self, failed: bool) -> None:
        """Count the item, then write outside the lock rather than across the I/O."""
        with self._lock:
            self._done += 1
            if failed:
                self._failed += 1
            done, failures = self._done, self._failed
        self._ctx.progress(done, self._total, failed=failures, note=self._note)


def fan_out(
    module: dspy.Module,
    examples: list[dspy.Example],
    ctx: StepContext,
    note: str,
    num_threads: int | None = None,
) -> list[Any]:
    """Run a module over every example and report progress"""
    return _Tracked(module, ctx, len(examples), note).batch(
        examples,
        num_threads=num_threads or MAX_CONCURRENCY,
        max_errors=len(examples) + 1,
        timeout=NO_STRAGGLER_RESUBMISSION,
    )
