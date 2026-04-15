from unittest.mock import patch

import pytest

from research_mapper.human_in_loop import validate_search_queries
from research_mapper.models import LuceneQuery


def _queries(*strings):
    return [LuceneQuery(query=s) for s in strings]


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_empty_input_keeps_all():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    with patch("research_mapper.human_in_loop.input", return_value=""):
        result = validate_search_queries(queries)
    assert result == queries


def test_select_subset():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    with patch("research_mapper.human_in_loop.input", return_value="1 3"):
        result = validate_search_queries(queries)
    assert len(result) == 2
    assert result[0].query == "climate AND health"
    assert result[1].query == "flood AND disease"


def test_select_single():
    queries = _queries("climate AND health")
    with patch("research_mapper.human_in_loop.input", return_value="1"):
        result = validate_search_queries(queries)
    assert len(result) == 1
    assert result[0].query == "climate AND health"


def test_whitespace_only_input_keeps_all():
    queries = _queries("climate AND health", "heat AND mortality")
    with patch("research_mapper.human_in_loop.input", return_value="   "):
        result = validate_search_queries(queries)
    assert result == queries


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_non_digit_token_raises():
    queries = _queries("climate AND health", "heat AND mortality")
    with patch("research_mapper.human_in_loop.input", return_value="1 abc"):
        with pytest.raises(ValueError, match="not a valid number"):
            validate_search_queries(queries)


def test_out_of_range_raises():
    queries = _queries("climate AND health", "heat AND mortality", "flood AND disease")
    with patch("research_mapper.human_in_loop.input", return_value="5"):
        with pytest.raises(ValueError, match="out of range"):
            validate_search_queries(queries)


def test_zero_index_raises():
    queries = _queries("climate AND health")
    with patch("research_mapper.human_in_loop.input", return_value="0"):
        with pytest.raises(ValueError, match="out of range"):
            validate_search_queries(queries)
