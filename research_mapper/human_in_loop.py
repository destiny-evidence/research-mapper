from typing import Sequence, T

from .models import LuceneQuery


def validate_search_queries(queries: list[LuceneQuery]) -> list[LuceneQuery]:
    print()
    print("Search queries the AI has generated:")
    print()
    for i, query in enumerate(queries, start=1):
        print(f"{i}: {query}")
    print()
    raw = input("Include (space-separated numbers, or Enter to keep all): ").strip()
    print()
    if not raw:
        return queries

    kept = []
    max_index = len(queries)
    for token in raw.split():
        if not token.isdigit():
            raise ValueError(f"'{token}' is not a valid number")
        n = int(token)
        if not (1 <= n <= max_index):
            raise ValueError(f"{n} is out of range (1-{max_index})")
        kept.append(queries[n - 1])  # user input is 1-indexed

    return kept


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
