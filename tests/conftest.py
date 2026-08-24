import uuid
from unittest.mock import MagicMock

import pytest
from destiny_sdk.enhancements import EnhancementType
from destiny_sdk.identifiers import DOIIdentifier
from dotenv import load_dotenv


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: end-to-end tests requiring live .env credentials"
    )


@pytest.fixture(scope="module")
def live_setup():
    """Load .env and configure DSPy + DESTINY client once per module."""
    import os

    load_dotenv()

    required = [
        "MAPPER_LLM_MODEL",
        "MAPPER_LLM_API_KEY",
        "MAPPER_LLM_BASE_URL",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        pytest.skip(f"Missing env vars: {missing}")

    from research_mapper.config import configure_dspy, get_destiny_client

    configure_dspy()
    get_destiny_client.cache_clear()


def _make_mock_reference(
    ref_id=None,
    doi="10.1000/test.doi",
    title="Test Paper Title",
    authors=("Author One", "Author Two"),
    year=2023,
    abstract_text="This is a test abstract.",
    pdf_url="https://example.com/paper.pdf",
):
    """Build a MagicMock shaped like a destiny_sdk Reference."""
    ref_id = ref_id or uuid.uuid4()

    # identifier
    mock_identifier = DOIIdentifier(identifier=doi)

    # BIBLIOGRAPHIC enhancement
    mock_author_1 = MagicMock()
    mock_author_1.display_name = authors[0]
    mock_author_2 = MagicMock()
    mock_author_2.display_name = authors[1]

    biblio_content = MagicMock()
    biblio_content.enhancement_type = EnhancementType.BIBLIOGRAPHIC
    biblio_content.title = title
    biblio_content.publication_year = year
    biblio_content.authorship = [mock_author_1, mock_author_2]
    biblio_content.publisher = None
    biblio_content.publication_venue = None
    biblio_content.pagination = None

    biblio_enhancement = MagicMock()
    biblio_enhancement.content = biblio_content

    # ABSTRACT enhancement
    abstract_content = MagicMock()
    abstract_content.enhancement_type = EnhancementType.ABSTRACT
    abstract_content.abstract = abstract_text

    abstract_enhancement = MagicMock()
    abstract_enhancement.content = abstract_content

    # LOCATION enhancement
    mock_location = MagicMock()
    mock_location.pdf_url = pdf_url
    mock_location.landing_page_url = None

    location_content = MagicMock()
    location_content.enhancement_type = EnhancementType.LOCATION
    location_content.locations = [mock_location]

    location_enhancement = MagicMock()
    location_enhancement.content = location_content

    ref = MagicMock()
    ref.id = ref_id
    ref.identifiers = [mock_identifier]
    ref.enhancements = [biblio_enhancement, abstract_enhancement, location_enhancement]

    return ref


@pytest.fixture
def mock_reference():
    return _make_mock_reference()


@pytest.fixture
def mock_destiny_client(mock_reference):
    mock_search_result = MagicMock()
    mock_search_result.references = [mock_reference]
    mock_search_result.total.count = 1
    mock_search_result.total.is_lower_bound = False

    client = MagicMock()
    client.search.return_value = mock_search_result
    client.lookup.return_value = [mock_reference]

    return client


APP_TABLES = (
    "artifacts",
    "decisions",
    "session_references",
    "operations",
    "research_sessions",
    "users",
)

LOCAL_DB = {
    "MAPPER_DB_HOST": "localhost:5433",
    "MAPPER_DB_NAME": "research_mapper",
    "MAPPER_DB_USER": "research_mapper",
    "MAPPER_DB_PASSWORD": "research_mapper",
}


@pytest.fixture(scope="session")
def database():
    """Migrate a real Postgres from scratch and yield its SessionFactory."""
    import os

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import OperationalError

    from research_mapper.config import init_database
    from research_mapper.db.session import db_manager

    for key, value in LOCAL_DB.items():
        os.environ.setdefault(key, value)

    init_database()
    try:
        with db_manager.engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"no Postgres at {os.environ['MAPPER_DB_HOST']}: {exc}")

    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return db_manager.session


@pytest.fixture
def session_factory(database):
    """A SessionFactory over an empty database."""
    from sqlalchemy import text

    with database() as db:
        db.execute(text(f"TRUNCATE {', '.join(APP_TABLES)} CASCADE"))
        db.commit()
    return database


@pytest.fixture
def db(session_factory):
    """A session for arranging and asserting, separate from the code under test."""
    with session_factory() as session:
        yield session


@pytest.fixture
def queued(database):
    """Empty the queue and yield a reader over it."""
    from sqlalchemy import text

    with database() as db:
        db.execute(text("TRUNCATE pgqueuer"))
        db.commit()

    def read() -> list[str]:
        with database() as db:
            return [
                bytes(row.payload).decode()
                for row in db.execute(
                    text("SELECT payload FROM pgqueuer WHERE entrypoint = 'operation'")
                ).all()
            ]

    return read
