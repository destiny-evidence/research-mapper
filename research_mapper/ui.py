import itertools
import sys
import textwrap
import threading
import time

from research_mapper.models import Evidence


class Spinner:
    _FRAMES = ["   ", ".  ", ".. ", "..."]

    def __init__(self, message: str = "Searching"):
        self._message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{self._message}{frame}")
            sys.stdout.flush()
            time.sleep(0.4)
        sys.stdout.write(f"\r{' ' * (len(self._message) + 4)}\r")
        sys.stdout.flush()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()


def print_evidence(evidence: list[Evidence], width: int = 70):
    print()
    for i, source in enumerate(evidence, 1):
        print("=" * width)
        print(
            textwrap.fill(f"[{i}] {source.title}" if source.title else "Unknown", width)
        )
        print("-" * width)
        print(textwrap.fill(source.abstract) if source.abstract else "Unknown")
    print("=" * width)
    print()
