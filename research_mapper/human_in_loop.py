from typing import Sequence, T


def parse_selection(raw: str, items: Sequence[T]) -> list[T]:
    if not raw:
        return items
    kept = []
    for token in raw.split():
        if not token.isdigit():
            raise ValueError(f"'{token}' is not a valid number")
        n = int(token)
        if not (1 <= n <= len(items)):
            raise ValueError(f"'{n} is out of range (1-{len(items)})")
        kept.append(items[n - 1])
    return kept
