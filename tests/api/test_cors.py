"""CORS is off unless MAPPER_CORS_ORIGINS names an origin."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from research_mapper.api.app import CORS_ORIGINS_VAR, configure_cors

ORIGIN = "https://stresearchmapperstaging.z6.web.core.windows.net"


def client(monkeypatch, value: str | None) -> TestClient:
    """A bare app configured for one value of the origins variable."""
    if value is None:
        monkeypatch.delenv(CORS_ORIGINS_VAR, raising=False)
    else:
        monkeypatch.setenv(CORS_ORIGINS_VAR, value)
    app = FastAPI()
    configure_cors(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def preflight(test_client: TestClient) -> dict[str, str]:
    """The response headers for a preflight of an authenticated GET."""
    response = test_client.options(
        "/healthz",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    return response.headers


@pytest.mark.parametrize("value", [None, "", "  ,  "])
def test_no_origins_means_no_cors_headers(monkeypatch, value):
    assert "access-control-allow-origin" not in preflight(client(monkeypatch, value))


def test_a_configured_origin_may_send_the_bearer_token(monkeypatch):
    headers = preflight(client(monkeypatch, ORIGIN))
    assert headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in headers["access-control-allow-headers"].lower()


def test_an_unlisted_origin_is_refused(monkeypatch):
    test_client = client(monkeypatch, "https://elsewhere.example.org")
    assert "access-control-allow-origin" not in preflight(test_client)


def test_origins_are_a_whitespace_tolerant_list(monkeypatch):
    test_client = client(monkeypatch, f"https://other.example.org , {ORIGIN}")
    assert preflight(test_client)["access-control-allow-origin"] == ORIGIN


def test_credentials_are_not_allowed(monkeypatch):
    """Auth is a bearer header, so cookies must never ride along."""
    assert "access-control-allow-credentials" not in preflight(
        client(monkeypatch, ORIGIN)
    )
