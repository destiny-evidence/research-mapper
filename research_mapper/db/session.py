"""Database connections."""

import os
from contextlib import AbstractContextManager, contextmanager
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

from azure.identity import DefaultAzureCredential
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

DB_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

credential = DefaultAzureCredential()


@dataclass(frozen=True, slots=True)
class DbSettings:
    """Where the database is and who we connect as."""

    user: str
    host: str
    db_name: str
    password: SecretStr | None


def db_settings() -> DbSettings:
    """Read the database connection settings from the environment."""
    password = os.environ.get("MAPPER_DB_PASSWORD")
    return DbSettings(
        user=os.environ["MAPPER_DB_USER"],
        host=os.environ["MAPPER_DB_HOST"],
        db_name=os.environ["MAPPER_DB_NAME"],
        password=SecretStr(password) if password else None,
    )


def db_password(settings: DbSettings) -> str:
    """Return the configured password, or a fresh Entra access token."""
    if settings.password is not None:
        return settings.password.get_secret_value()
    return credential.get_token(DB_SCOPE).token


class DatabaseSessionManager:
    """Manages database sessions."""

    def __init__(self) -> None:
        """Init DatabaseSessionManager."""
        self._engine: Engine | None = None
        self._sessionmaker: sessionmaker[Session] | None = None

    def init(self, settings: DbSettings | None = None) -> None:
        """Initialize the database manager."""
        settings = settings or db_settings()
        if settings.password:
            self._engine = create_engine(
                url=f"postgresql+psycopg://{settings.user}:{settings.password.get_secret_value()}@{settings.host}/{settings.db_name}",
                pool_pre_ping=True,
            )
        else:
            self._engine = create_engine(
                url=f"postgresql+psycopg://{settings.user}@{settings.host}/{settings.db_name}",
                pool_pre_ping=True,
                connect_args={"sslmode": "require"},
            )

            # This is (more or less) as recommended in SQLAlchemy docs
            # https://docs.sqlalchemy.org/en/20/core/engines.html#generating-dynamic-authentication-tokens
            # https://docs.sqlalchemy.org/en/20/dialects/mssql.html#mssql-pyodbc-access-tokens

            # Cold boot is slow - here we kick off the first token retrieval
            # so that the first request is not delayed by it.
            credential.get_token(DB_SCOPE)

            @event.listens_for(self._engine, "do_connect")
            def provide_token(
                _dialect: Dialect,
                _conn_rec: ConnectionPoolEntry,
                _cargs: list[Any],
                cparams: dict[str, Any],
            ) -> None:
                cparams["password"] = credential.get_token(DB_SCOPE).token

        self._sessionmaker = sessionmaker(bind=self._engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        """The underlying engine."""
        if self._engine is None:
            msg = "DatabaseSessionManager is not initialized"
            raise RuntimeError(msg)
        return self._engine

    def close(self) -> None:
        """Close all database connections and dispose of references."""
        if self._engine is None:
            return
        self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Yield a database session."""
        if self._sessionmaker is None:
            msg = "DatabaseSessionManager is not initialized"
            raise RuntimeError(msg)
        with self._sessionmaker() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    @contextmanager
    def connect(self) -> Generator[Connection, None, None]:
        """Yield a database connection."""
        if self._engine is None:
            msg = "DatabaseSessionManager is not initialized"
            raise RuntimeError(msg)
        with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise


db_manager = DatabaseSessionManager()


def get_session() -> Generator[Session, None, None]:
    """Yield a session, for use as a dependency."""
    with db_manager.session() as session:
        yield session


SessionFactory = Callable[[], AbstractContextManager[Session]]
