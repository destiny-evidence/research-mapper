import pytest

from research_mapper.human_in_loop import parse_selection
from research_mapper.models import LuceneQuery


def _queries(*strings):
    return [LuceneQuery(query=s) for s in strings]


# ---------------------------------------------------------------------------
# Positive cases
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


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


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
