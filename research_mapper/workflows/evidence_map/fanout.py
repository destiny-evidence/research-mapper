"""Glue for driving dspy fan-outs from a step."""

import threading
from typing import Any

import dspy

from research_mapper.engine.context import StepContext

NO_STRAGGLER_RESUBMISSION = 0

MAX_CONCURRENCY = 8


class ProgressTracker:
    def __init__(self, ctx: StepContext, total: int, note: str, done: int = 0):
        self._ctx = ctx
        self._total = total
        self._note = note
        self._done = done
        self._failed = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._ctx.progress(self._done, self._total, note=self._note)

    def fan_out(
        self,
        module: dspy.Module,
        examples: list[dspy.Example],
        num_threads: int | None = None,
    ) -> list[Any]:
        return _Tracked(module, self).batch(
            examples,
            num_threads=num_threads or MAX_CONCURRENCY,
            max_errors=len(examples) + 1,
            timeout=NO_STRAGGLER_RESUBMISSION,
        )

    @property
    def failed(self) -> int:
        with self._lock:
            return self._failed

    def report(self, failed: bool) -> None:
        with self._lock:
            self._done += 1
            if failed:
                self._failed += 1
            done, failures = self._done, self._failed
        self._ctx.progress(done, self._total, failed=failures, note=self._note)


class _Tracked(dspy.Module):
    def __init__(self, inner: dspy.Module, tracker: ProgressTracker):
        self._inner = inner
        self._tracker = tracker

    def forward(self, **inputs: Any) -> dspy.Prediction:
        try:
            prediction = self._inner(**inputs)
        except Exception:
            self._tracker.report(failed=True)
            raise
        self._tracker.report(failed=False)
        return prediction
