from research_mapper.engine.models import Operation, ResearchSession, User


def make_user(db, subject="local", issuer="local") -> User:
    """Persist a user."""
    user = User(issuer=issuer, subject=subject)
    db.add(user)
    db.commit()
    return user


def make_session(db, user, question="Does X affect Y?") -> ResearchSession:
    """Persist a research session owned by a user."""
    session = ResearchSession(
        user_id=user.id,
        workflow="evidence_map",
        question=question,
        community="hpv",
    )
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
