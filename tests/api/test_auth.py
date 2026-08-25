import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from research_mapper.api import auth
from research_mapper.api.app import app
from research_mapper.api.deps import get_session_factory
from research_mapper.config import init_database
from research_mapper.engine.models import ResearchSession, User

ISSUER = "https://auth.example.org/realms/destiny"
CLIENT_ID = "research-mapper-ui-staging"
SUBJECT = "8b0c0f4e-0000-4000-8000-000000000001"
SESSION = {"workflow": "evidence_map", "question": "q", "community": "hpv"}

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeKeys:
    """Stands in for the JWKS endpoint."""

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": KEY.public_key()})()


def token(**overrides) -> str:
    """A Keycloak-shaped access token, signed with the key the app will trust."""
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": CLIENT_ID,
        "iat": now,
        "exp": now + 300,
        "resource_access": {CLIENT_ID: {"roles": [auth.REQUIRED_ROLE]}},
    } | overrides
    return jwt.encode(claims, KEY, algorithm="RS256")


def bearer(**overrides) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(**overrides)}"}


@pytest.fixture
def client(session_factory):
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    init_database()
    app.dependency_overrides.clear()


@pytest.fixture
def keycloak(monkeypatch):
    """Turn auth on, against a signing key the test controls."""
    monkeypatch.setenv("MAPPER_AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("MAPPER_AUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(auth, "keys", lambda issuer: FakeKeys())


def test_unconfigured_means_no_auth(client, db):
    assert client.post("/sessions/", json=SESSION).status_code == 201
    user = db.execute(select(User)).scalar_one()
    assert (user.issuer, user.subject) == auth.LOCAL_PRINCIPAL


def test_a_missing_token_is_a_401(client, keycloak):
    reply = client.get("/sessions/")
    assert reply.status_code == 401
    assert reply.headers["WWW-Authenticate"] == "Bearer"


def test_a_valid_token_identifies_the_caller(client, keycloak, db):
    assert client.post("/sessions/", json=SESSION, headers=bearer()).status_code == 201
    user = db.execute(select(User)).scalar_one()
    assert (user.issuer, user.subject) == (ISSUER, SUBJECT)


def test_a_token_without_the_role_is_a_403(client, keycloak):
    headers = bearer(resource_access={CLIENT_ID: {"roles": ["someone_else"]}})
    assert client.get("/sessions/", headers=headers).status_code == 403


def test_a_token_for_another_audience_is_a_401(client, keycloak):
    assert (
        client.get("/sessions/", headers=bearer(aud="taxonomy-ui")).status_code == 401
    )


def test_an_expired_token_is_a_401(client, keycloak):
    stale = int(time.time()) - 60
    assert client.get("/sessions/", headers=bearer(exp=stale)).status_code == 401


def test_another_users_session_is_a_404(client, keycloak, db, session_factory):
    created = client.post("/sessions/", json=SESSION, headers=bearer()).json()

    stranger = User(issuer=ISSUER, subject="someone-else")
    db.add(stranger)
    db.commit()
    theirs = ResearchSession(
        user_id=stranger.id, workflow="evidence_map", question="q", community="hpv"
    )
    db.add(theirs)
    db.commit()

    assert client.get(f"/sessions/{theirs.id}/", headers=bearer()).status_code == 404
    listed = client.get("/sessions/", headers=bearer()).json()
    assert [row["id"] for row in listed] == [created["id"]]


def test_healthz_stays_open(client, keycloak):
    """A 401 here would fail the container's liveness probe."""
    assert client.get("/healthz").status_code == 200
