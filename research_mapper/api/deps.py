from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_mapper.db.session import SessionFactory, db_manager
from research_mapper.engine.models import ResearchSession, User

LOCAL_USER = ("local", "local")


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""
    with db_manager.session() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]


def get_session_factory() -> SessionFactory:
    """The factory the engine opens its own transactions from."""
    return db_manager.session


Factory = Annotated[SessionFactory, Depends(get_session_factory)]


def current_user(db: DbSession) -> User:
    """Return the one local user. Becomes the EasyAuth lookup when auth lands."""
    issuer, subject = LOCAL_USER
    user = db.execute(
        select(User).where(User.issuer == issuer).where(User.subject == subject)
    ).scalar_one_or_none()
    if user is None:
        user = User(issuer=issuer, subject=subject)
        db.add(user)
        db.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def get_session(db: DbSession, session_id: Annotated[UUID, Path()]) -> ResearchSession:
    """Return a research session, or 404."""
    research_session = db.get(ResearchSession, session_id)
    if research_session is None:
        raise HTTPException(404, "session not found")
    return research_session


SessionOr404 = Annotated[ResearchSession, Depends(get_session)]
