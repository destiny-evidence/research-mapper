from pathlib import Path
from typing import Sequence, T


def parse_yes_no(raw: str, default: bool = False) -> bool:
    """
    Parses a raw yes/no response, returning the default when input is empty.
    :param raw: the raw user input
    :param default: the value to return for empty input
    :return: True for yes, False for no
    """
    normalised = raw.strip().lower()
    if not normalised:
        return default
    if normalised in ("y", "yes"):
        return True
    if normalised in ("n", "no"):
        return False
    raise ValueError(f"'{raw}' is not a valid response — enter y or n")


def parse_file_path(raw: str, default: str) -> Path:
    """
    Parses a raw file path input, returning the default path when input is empty.
    :param raw: the raw user input
    :param default: the filename to use when input is empty
    :return: a Path object
    """
    return Path(raw.strip() if raw.strip() else default)


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
