"""API dependencies."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research_mapper.api import auth
from research_mapper.db.session import SessionFactory, db_manager
from research_mapper.engine.models import ResearchSession, User


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""
    with db_manager.session() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]
Principal = Annotated[auth.Principal, Depends(auth.principal)]


def get_session_factory() -> SessionFactory:
    """The factory the engine opens its own transactions from."""
    return db_manager.session


Factory = Annotated[SessionFactory, Depends(get_session_factory)]


def current_user(db: DbSession, who: Principal) -> User:
    """Get or create the row for the authenticated caller."""
    issuer, subject = who
    lookup = select(User).where(User.issuer == issuer).where(User.subject == subject)
    user = db.execute(lookup).scalar_one_or_none()
    if user is None:
        try:
            user = User(issuer=issuer, subject=subject)
            db.add(user)
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.execute(lookup).scalar_one()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def get_session(
    db: DbSession, user: CurrentUser, session_id: Annotated[UUID, Path()]
) -> ResearchSession:
    """Return any research session, or 404.

    Sessions are readable and writable by any authenticated caller so that a
    shared link opens for whoever follows it.
    """
    research_session = db.get(ResearchSession, session_id)
    if research_session is None:
        raise HTTPException(404, "session not found")
    return research_session


SessionOr404 = Annotated[ResearchSession, Depends(get_session)]
