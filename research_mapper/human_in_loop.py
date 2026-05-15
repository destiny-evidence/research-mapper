from typing import Sequence, T


def parse_selection(raw: str, items: Sequence[T]) -> list[T]:
    """
    Parses and processes raw user input selecting a subset of enumerated items.
    :param raw: the raw user input to parse
    :param items: the collection of enumerated items to select from
    :return: the subset of user selected items
    """
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
