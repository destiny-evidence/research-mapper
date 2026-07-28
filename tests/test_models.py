import uuid

import pytest
from destiny_sdk.identifiers import DOIIdentifier
from pydantic import ValidationError

from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import ClarificationOptions


# ---------------------------------------------------------------------------
# UserQuery
# ---------------------------------------------------------------------------


def test_user_query_stores_text():
    q = UserQuery(query="what causes climate change")
    assert q.query == "what causes climate change"


# ---------------------------------------------------------------------------
# LuceneQuery validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query_str",
    [
        "climate AND health",
        "title:cancer",
        "author:smith AND year:[2020 TO 2024]",
        "simple",
        '"exact phrase"',
    ],
)
def test_lucene_query_valid(query_str):
    lq = LuceneQuery(query=query_str)
    assert lq.query == query_str


@pytest.mark.parametrize(
    "bad_query",
    [
        "AND OR",
        "((unclosed",
        "field::double_colon",
    ],
)
def test_lucene_query_invalid_syntax_raises(bad_query):
    with pytest.raises(ValueError, match="Invalid Lucene syntax"):
        LuceneQuery(query=bad_query)


# ---------------------------------------------------------------------------
# Evidence.__hash__ / __eq__ deduplication
# ---------------------------------------------------------------------------


def _evidence(ref_id=None, doi="10.1000/same") -> Evidence:
    return Evidence(
        destiny_id=ref_id or uuid.uuid4(),
        external_identifiers=[DOIIdentifier(identifier=doi)],
    )


def test_evidence_hash_deduplication():
    ref_id = uuid.uuid4()
    ev_a = _evidence(ref_id=ref_id)
    ev_b = _evidence(ref_id=ref_id)

    result = {ev_a, ev_b}
    assert len(result) == 1


def test_evidence_hash_different_ids():
    ev_a = _evidence(ref_id=uuid.uuid4())
    ev_b = _evidence(ref_id=uuid.uuid4())

    result = {ev_a, ev_b}
    assert len(result) == 2


def test_evidences_with_same_hash_are_equal():
    ref_id = uuid.uuid4()
    ev_a = _evidence(ref_id=ref_id)
    ev_b = _evidence(ref_id=ref_id)

    assert hash(ev_a) == hash(ev_b)
    assert ev_a == ev_b


def test_evidences_with_different_hash_are_not_equal():
    ev_a = _evidence(ref_id=uuid.uuid4())
    ev_b = _evidence(ref_id=uuid.uuid4())

    assert hash(ev_a) != hash(ev_b)
    assert ev_a != ev_b


# ---------------------------------------------------------------------------
# Evidence.__str__
# ---------------------------------------------------------------------------


def test_evidence_to_str_uses_destiny_id_when_no_title_or_abstract_available():
    destiny_id = uuid.uuid4()
    ev_a = Evidence(
        destiny_id=destiny_id,
    )

    assert str(ev_a) == str(destiny_id)


def test_evidence_to_str_uses_title_when_only_title_available():
    title = "This is a paper!"
    ev_a = Evidence(
        destiny_id=uuid.uuid4(),
        title=title,
    )

    assert str(ev_a) == f"{title} - "


def test_evidence_to_str_uses_abstract_when_only_abstract_available():
    abstract = "This is an important abstract!"
    ev_a = Evidence(
        destiny_id=uuid.uuid4(),
        abstract=abstract,
    )

    assert str(ev_a) == f" - {abstract}"


def test_evidence_to_str_uses_title_andabstract_when_both_available():
    title = "This is a paper!"
    abstract = "This is an important abstract!"
    ev_a = Evidence(destiny_id=uuid.uuid4(), title=title, abstract=abstract)

    assert str(ev_a) == f"{title} - {abstract}"


# ---------------------------------------------------------------------------
# ClarificationOptions validation
# ---------------------------------------------------------------------------


def test_clarification_options_accepts_one_or_more_options():
    opts = ClarificationOptions(question="Which do you mean?", options=["A", "B"])
    assert opts.options == ["A", "B"]


def test_clarification_options_rejects_empty_options():
    with pytest.raises(ValidationError):
        ClarificationOptions(question="Which do you mean?", options=[])
