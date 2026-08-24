from uuid import UUID, uuid4

import pytest

from conftest import _make_mock_reference
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import hydrate


class FakeClient:
    """Echoes back a reference per requested id, recording each batch."""

    def __init__(self) -> None:
        self.batches: list[list[UUID]] = []

    def lookup(self, lookups, timeout=None):
        ids = [UUID(lookup.identifier) for lookup in lookups]
        self.batches.append(ids)
        return [_make_mock_reference(ref_id=identifier) for identifier in ids]


@pytest.fixture
def client(monkeypatch) -> FakeClient:
    fake = FakeClient()
    monkeypatch.setattr(hydrate, "get_destiny_client", lambda: fake)
    return fake


def test_yields_evidence_keyed_by_destiny_id(client):
    ids = [uuid4() for _ in range(3)]

    pages = list(hydrate.get_references(ids))

    assert len(pages) == 1
    assert sorted(pages[0]) == sorted(ids)
    assert all(isinstance(item, Evidence) for item in pages[0].values())
    assert all(key == item.destiny_id for key, item in pages[0].items())


def test_lookups_are_chunked_to_destinys_cap(client):
    """DESTINY caps a lookup at 100, so a thousand-reference map is ten calls."""
    ids = [uuid4() for _ in range(250)]

    pages = list(hydrate.get_references(ids))

    assert [len(batch) for batch in client.batches] == [100, 100, 50]
    assert [len(page) for page in pages] == [100, 100, 50]


def test_no_ids_means_no_calls(client):
    assert list(hydrate.get_references([])) == []
    assert client.batches == []


def test_nothing_is_fetched_until_a_page_is_consumed(client):
    """It's a generator: the caller controls when DESTINY gets hit."""
    pages = hydrate.get_references([uuid4() for _ in range(150)])

    assert client.batches == []
    next(pages)
    assert len(client.batches) == 1
