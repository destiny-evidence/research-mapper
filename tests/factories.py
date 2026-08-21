from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.engine.models import Operation, ResearchSession, User


def make_user(db, subject="user-1") -> User:
    """Persist a user."""
    user = User(issuer="https://login.example", subject=subject)
    db.add(user)
    db.commit()
    return user


def make_session(db, user, question="Does X affect Y?") -> ResearchSession:
    """Persist a research session owned by a user."""
    session = ResearchSession(user_id=user.id, question=question, community="climate")
    db.add(session)
    db.commit()
    return session


def make_operation(db, session, user, type="noop", **kwargs) -> Operation:
    """Persist an operation on a session."""
    operation = Operation(
        research_session_id=session.id,
        created_by_id=user.id,
        type=type,
        **kwargs,
    )
    db.add(operation)
    db.commit()
    return operation


def make_reference(db, session, destiny_id, **kwargs) -> SessionReference:
    """Persist a session reference."""
    reference = SessionReference(
        research_session_id=session.id, destiny_id=destiny_id, **kwargs
    )
    db.add(reference)
    db.commit()
    return reference
