from unittest.mock import patch

from destiny_sdk.search import AnnotationFilter

from research_mapper.concept_search import retrieve_evidence_by_concepts
from research_mapper.models.common import Evidence
from research_mapper.taxonomy import RepoCommunity


def test_retrieve_evidence_by_concepts_returns_evidence(
    mock_destiny_client, mock_reference
):
    with patch(
        "research_mapper.concept_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = retrieve_evidence_by_concepts(
            RepoCommunity.HPV, ["https://vocab.example.org/A"]
        )

    assert len(result) == 1
    assert isinstance(result[0], Evidence)


def test_retrieve_evidence_by_concepts_applies_domain_inclusion_annotation(
    mock_destiny_client,
):
    with patch(
        "research_mapper.concept_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        retrieve_evidence_by_concepts(
            RepoCommunity.HPV, ["https://vocab.example.org/A"]
        )

    mock_destiny_client.search.assert_called_once_with(
        query="*",
        concepts=["https://vocab.example.org/A"],
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        timeout=60,
    )


def test_retrieve_evidence_by_concepts_uses_correct_label_for_esea(
    mock_destiny_client,
):
    with patch(
        "research_mapper.concept_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        retrieve_evidence_by_concepts(RepoCommunity.ESEA, [])

    mock_destiny_client.search.assert_called_once_with(
        query="*",
        concepts=[],
        annotations=[
            AnnotationFilter(scheme="domain-inclusion", label="jacobs-education")
        ],
        timeout=60,
    )


def test_retrieve_evidence_by_concepts_empty_results(mock_destiny_client):
    mock_destiny_client.search.return_value.references = []
    with patch(
        "research_mapper.concept_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = retrieve_evidence_by_concepts(RepoCommunity.HPV, [])

    assert result == []
