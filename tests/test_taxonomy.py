import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from rdflib import Graph

from research_mapper.taxonomy import (
    RepoCommunity,
    TaxonomyFetchError,
    build_concept_index,
    get_graph,
    get_taxonomy,
)


@pytest.fixture(autouse=True)
def _clear_taxonomy_cache():
    """get_taxonomy is lru_cache'd; tests mock httpx.get differently per case, so the
    cache must be cleared before (and after) each test to avoid leaking results."""
    get_taxonomy.cache_clear()
    yield
    get_taxonomy.cache_clear()


_CONTEXT = {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "dct": "http://purl.org/dc/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
}


def _vocab(graph: list[dict]) -> dict:
    return {"@context": _CONTEXT, "@graph": graph}


def _graph(vocab: dict) -> Graph:
    """Parses a vocab dict into an rdflib Graph the same way get_graph does —
    build_concept_index takes a Graph, not a raw JSON-LD dict."""
    graph = Graph()
    graph.parse(data=json.dumps(vocab), format="json-ld")
    return graph


# ---------------------------------------------------------------------------
# build_concept_index — expanding JSON-LD into a flat, LLM-facing concept index
# ---------------------------------------------------------------------------


def test_build_concept_index_extracts_labels_and_scheme():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/Country",
                "@type": "skos:ConceptScheme",
                "dct:title": "Country",
            },
            {
                "@id": "https://example.org/vocab/Country/KE",
                "@type": "skos:Concept",
                "skos:inScheme": {"@id": "https://example.org/vocab/Country"},
                "skos:prefLabel": "Kenya",
            },
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert len(indexed.concepts) == 1
    concept = indexed.concepts[0]
    assert concept.scheme == "Country"
    assert concept.label == "Kenya"
    assert concept.alt_labels == []
    assert concept.detail is None
    assert (
        indexed.local_ref_to_iri[concept.local_ref]
        == "https://example.org/vocab/Country/KE"
    )


def test_build_concept_index_prefers_definition_over_scope_note():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/StudyDesign/RCT",
                "@type": "skos:Concept",
                "skos:prefLabel": "RCT",
                "skos:definition": "A randomised controlled trial.",
                "skos:scopeNote": "Use for randomised designs.",
            }
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert indexed.concepts[0].detail == "A randomised controlled trial."


def test_build_concept_index_falls_back_to_scope_note_without_definition():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/StudyDesign/RCT",
                "@type": "skos:Concept",
                "skos:prefLabel": "RCT",
                "skos:scopeNote": "Use for randomised designs.",
            }
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert indexed.concepts[0].detail == "Use for randomised designs."


def test_build_concept_index_handles_missing_definition_and_scope_note():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/StudyDesign/RCT",
                "@type": "skos:Concept",
                "skos:prefLabel": "RCT",
            }
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert indexed.concepts[0].detail is None


def test_build_concept_index_normalises_single_and_multiple_alt_labels():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/A",
                "@type": "skos:Concept",
                "skos:prefLabel": "A",
                "skos:altLabel": "SingleAlt",
            },
            {
                "@id": "https://example.org/vocab/B",
                "@type": "skos:Concept",
                "skos:prefLabel": "B",
                "skos:altLabel": ["Alt1", "Alt2"],
            },
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    by_label = {c.label: c for c in indexed.concepts}
    assert by_label["A"].alt_labels == ["SingleAlt"]
    assert set(by_label["B"].alt_labels) == {"Alt1", "Alt2"}


def test_build_concept_index_defaults_scheme_to_other_when_missing():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/Orphan",
                "@type": "skos:Concept",
                "skos:prefLabel": "Orphan concept",
            }
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert indexed.concepts[0].scheme == "Other"


def test_build_concept_index_excludes_non_skos_nodes():
    """Ontology-fragment nodes (owl:Class, owl:ObjectProperty) aren't taxonomy concepts."""
    vocab = _vocab(
        [
            {"@id": "https://example.org/vocab#Investigation", "@type": "owl:Class"},
            {
                "@id": "https://example.org/vocab/A",
                "@type": "skos:Concept",
                "skos:prefLabel": "A",
            },
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert len(indexed.concepts) == 1
    assert indexed.concepts[0].label == "A"


def test_build_concept_index_sorts_by_scheme_then_label():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/S1",
                "@type": "skos:ConceptScheme",
                "dct:title": "Zeta",
            },
            {
                "@id": "https://example.org/vocab/S2",
                "@type": "skos:ConceptScheme",
                "dct:title": "Alpha",
            },
            {
                "@id": "https://example.org/vocab/Z1",
                "@type": "skos:Concept",
                "skos:inScheme": {"@id": "https://example.org/vocab/S1"},
                "skos:prefLabel": "B concept",
            },
            {
                "@id": "https://example.org/vocab/A1",
                "@type": "skos:Concept",
                "skos:inScheme": {"@id": "https://example.org/vocab/S2"},
                "skos:prefLabel": "A concept",
            },
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    assert [c.scheme for c in indexed.concepts] == ["Alpha", "Zeta"]
    assert indexed.concepts[0].local_ref == "C0"
    assert indexed.concepts[1].local_ref == "C1"


def test_build_concept_index_resolve_maps_local_refs_to_correct_iris():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/A",
                "@type": "skos:Concept",
                "skos:prefLabel": "A",
            },
            {
                "@id": "https://example.org/vocab/B",
                "@type": "skos:Concept",
                "skos:prefLabel": "B",
            },
        ]
    )

    indexed = build_concept_index(_graph(vocab))

    a = next(c for c in indexed.concepts if c.label == "A")
    b = next(c for c in indexed.concepts if c.label == "B")
    assert indexed.resolve([a.local_ref, b.local_ref]) == [
        "https://example.org/vocab/A",
        "https://example.org/vocab/B",
    ]


# ---------------------------------------------------------------------------
# get_graph — the single rdflib-backed loader build_concept_index and the
# taxonomy browsing tools are both built from
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    get_graph.cache_clear()
    yield
    get_graph.cache_clear()


def test_get_graph_parses_the_fetched_vocab_into_a_graph():
    vocab = _vocab(
        [
            {
                "@id": "https://example.org/vocab/A",
                "@type": "skos:Concept",
                "skos:prefLabel": "A",
            }
        ]
    )

    with patch("research_mapper.taxonomy.get_taxonomy", return_value=vocab):
        graph = get_graph(RepoCommunity.HPV)

    indexed = build_concept_index(graph)
    assert [c.label for c in indexed.concepts] == ["A"]


def test_get_graph_is_cached():
    with patch(
        "research_mapper.taxonomy.get_taxonomy", return_value=_vocab([])
    ) as mock_get_taxonomy:
        get_graph(RepoCommunity.HPV)
        get_graph(RepoCommunity.HPV)

    mock_get_taxonomy.assert_called_once()


# ---------------------------------------------------------------------------
# get_taxonomy — defensive fetch of the raw vocabulary document
# ---------------------------------------------------------------------------


def test_get_taxonomy_returns_parsed_json():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"@context": {}, "@graph": []}

    with patch("research_mapper.taxonomy.httpx.get", return_value=mock_response):
        result = get_taxonomy(RepoCommunity.HPV)

    assert result == {"@context": {}, "@graph": []}


def test_get_taxonomy_raises_on_http_status_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock()
    )

    with (
        patch("research_mapper.taxonomy.httpx.get", return_value=mock_response),
        pytest.raises(TaxonomyFetchError, match="Could not fetch"),
    ):
        get_taxonomy(RepoCommunity.HPV)


def test_get_taxonomy_raises_on_connection_error():
    with (
        patch(
            "research_mapper.taxonomy.httpx.get",
            side_effect=httpx.ConnectError("no route"),
        ),
        pytest.raises(TaxonomyFetchError, match="Could not fetch"),
    ):
        get_taxonomy(RepoCommunity.HPV)


def test_get_taxonomy_raises_on_invalid_json():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("not json")

    with (
        patch("research_mapper.taxonomy.httpx.get", return_value=mock_response),
        pytest.raises(TaxonomyFetchError, match="Invalid JSON"),
    ):
        get_taxonomy(RepoCommunity.HPV)
