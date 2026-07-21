from pathlib import Path

import pytest

from research_mapper.human_in_loop import parse_file_path, parse_selection, parse_yes_no
from research_mapper.models.sparse_search import LuceneQuery


def _queries(*strings):
    return [LuceneQuery(query=s) for s in strings]


# ---------------------------------------------------------------------------
# parse_selection — filtering suggested items via index selection
# (e.g. screening criteria, search results)
# ---------------------------------------------------------------------------


def test_empty_input_keeps_all():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    result = parse_selection("", queries)
    assert result == queries


def test_select_subset():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    result = parse_selection("1 3", queries)
    assert len(result) == 2
    assert result[0].query == "climate AND health"
    assert result[1].query == "flood AND disease"


def test_select_single():
    queries = _queries("climate AND health")
    result = parse_selection("1", queries)
    assert len(result) == 1
    assert result[0].query == "climate AND health"


def test_whitespace_only_input_returns_empty():
    queries = _queries("climate AND health", "heat AND mortality")
    result = parse_selection("   ", queries)
    assert result == []


def test_non_digit_token_raises():
    queries = _queries("climate AND health", "heat AND mortality")
    with pytest.raises(ValueError, match="not a valid number"):
        parse_selection("1 abc", queries)


def test_out_of_range_raises():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    with pytest.raises(ValueError, match="out of range"):
        parse_selection("5", queries)


def test_zero_index_raises():
    queries = _queries("climate AND health")
    with pytest.raises(ValueError, match="out of range"):
        parse_selection("0", queries)


# ---------------------------------------------------------------------------
# parse_yes_no — yes/no confirmation gates
# (e.g. "export results to a file?", "accept these dimensions?")
# ---------------------------------------------------------------------------


def test_parse_yes_no_empty_returns_default():
    assert parse_yes_no("", default=True) is True
    assert parse_yes_no("   ", default=False) is False


@pytest.mark.parametrize("raw", ["y", "Y", "yes", "YES"])
def test_parse_yes_no_accepts_yes_variants(raw):
    assert parse_yes_no(raw) is True


@pytest.mark.parametrize("raw", ["n", "N", "no", "NO"])
def test_parse_yes_no_accepts_no_variants(raw):
    assert parse_yes_no(raw) is False


def test_parse_yes_no_invalid_raises():
    with pytest.raises(ValueError, match="not a valid response"):
        parse_yes_no("maybe")


# ---------------------------------------------------------------------------
# parse_file_path — resolving an export path, falling back to a default
# ---------------------------------------------------------------------------


def test_parse_file_path_empty_returns_default():
    assert parse_file_path("", default="results.ris") == Path("results.ris")


def test_parse_file_path_whitespace_only_returns_default():
    assert parse_file_path("   ", default="results.ris") == Path("results.ris")


def test_parse_file_path_uses_provided_path():
    assert parse_file_path("output/my_export.ris", default="results.ris") == Path(
        "output/my_export.ris"
    )


def test_parse_file_path_strips_surrounding_whitespace():
    assert parse_file_path("  my_export.ris  ", default="results.ris") == Path(
        "my_export.ris"
    )
