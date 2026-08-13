from unittest.mock import MagicMock, patch

import pytest

from research_mapper.models.common import UserQuery
from research_mapper.models.taxonomy_search import Concept, IndexedVocab
from research_mapper.modules.taxonomy_mapping import TaxonomySchemeDimensionGenerator


def _indexed_vocab() -> IndexedVocab:
    concepts = [
        Concept(local_ref="C0", scheme="Country", label="Kenya"),
        Concept(local_ref="C1", scheme="Country", label="Uganda"),
        Concept(local_ref="C2", scheme="Study Design", label="RCT"),
        Concept(local_ref="C3", scheme="Study Design", label="Cohort"),
        Concept(local_ref="C4", scheme="Outcome", label="Mortality"),
    ]
    local_ref_to_iri = {
        c.local_ref: f"https://vocab.example.org/{c.local_ref}" for c in concepts
    }
    return IndexedVocab(concepts=concepts, local_ref_to_iri=local_ref_to_iri)


def _mock_chain_of_thought(scheme1: str, scheme2: str, scheme3: str) -> MagicMock:
    prediction = MagicMock(scheme1=scheme1, scheme2=scheme2, scheme3=scheme3)
    prediction.reasoning = "some reasoning"
    mock_predictor = MagicMock(return_value=prediction)
    return MagicMock(return_value=mock_predictor)


def test_forward_builds_dimensions_from_chosen_schemes():
    """Each chosen scheme becomes a dimension with all of that scheme's concepts as
    subtopics, as-is — no LLM curation of subtopics for the taxonomy mapping path."""
    generator = TaxonomySchemeDimensionGenerator()
    indexed = _indexed_vocab()

    with patch(
        "research_mapper.modules.taxonomy_mapping.dspy.ChainOfThought",
        _mock_chain_of_thought("Country", "Study Design", "Outcome"),
    ):
        prediction = generator.forward(
            user_query=UserQuery(query="test"),
            indexed_vocab=indexed,
            available_schemes=["Country", "Study Design", "Outcome"],
        )

    assert prediction.dimension1.name == "Country"
    assert {s.name for s in prediction.dimension1.subtopics} == {"Kenya", "Uganda"}
    assert prediction.dimension2.name == "Study Design"
    assert {s.name for s in prediction.dimension2.subtopics} == {"RCT", "Cohort"}
    assert prediction.dimension3.name == "Outcome"
    assert {s.name for s in prediction.dimension3.subtopics} == {"Mortality"}
    assert prediction.reasoning == "some reasoning"


def test_forward_raises_on_duplicate_scheme_picks():
    """
    Regression test: Literal only constrains scheme1/2/3 to valid *membership*, not
    *distinctness* across the 3 fields — an LLM picking the same scheme twice must be
    caught explicitly rather than silently producing a degenerate 2-dimension map.
    """
    generator = TaxonomySchemeDimensionGenerator()
    indexed = _indexed_vocab()

    with (
        patch(
            "research_mapper.modules.taxonomy_mapping.dspy.ChainOfThought",
            _mock_chain_of_thought("Country", "Country", "Outcome"),
        ),
        pytest.raises(RuntimeError, match="Country"),
    ):
        generator.forward(
            user_query=UserQuery(query="test"),
            indexed_vocab=indexed,
            available_schemes=["Country", "Study Design", "Outcome"],
        )


def test_forward_raises_when_fewer_than_3_schemes_available():
    generator = TaxonomySchemeDimensionGenerator()
    indexed = _indexed_vocab()

    with pytest.raises(RuntimeError, match="at least 3"):
        generator.forward(
            user_query=UserQuery(query="test"),
            indexed_vocab=indexed,
            available_schemes=["Country", "Study Design"],
        )
