import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock

import httpx
import pytest
from destiny_sdk.keycloak_auth import TokenResponse

from research_mapper.config import _destiny_auth
from research_mapper.local_destiny_auth import (
    RefreshTokenAuth,
    auth_code_flow,
    start_relay,
)


def token(access: str, refresh: str | None = "refresh-2") -> TokenResponse:
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=300,
        token_type="Bearer",
        scope="openid",
    )


def flow(*responses: TokenResponse) -> MagicMock:
    fake = MagicMock()
    fake.refresh_token.side_effect = responses
    return fake


def run(auth: RefreshTokenAuth, *statuses: int) -> list[str]:
    """Drive the auth flow against canned responses, returning each token it sent.

    httpx re-yields the same request object, so the header has to be read as it goes.
    """
    request = httpx.Request("GET", "https://destiny.example/v1/references/")
    generator = auth.auth_flow(request)
    sent = [next(generator).headers["Authorization"]]
    for status in statuses:
        try:
            sent.append(
                generator.send(httpx.Response(status, request=request)).headers[
                    "Authorization"
                ]
            )
        except StopIteration:
            break
    return sent


def test_the_refresh_token_buys_an_access_token():
    auth = RefreshTokenAuth(flow(token("access-1")), "refresh-1")

    assert run(auth, 200) == ["Bearer access-1"]


def test_the_access_token_is_reused_across_requests():
    """One exchange per process, not one per request."""
    fake = flow(token("access-1"))
    auth = RefreshTokenAuth(fake, "refresh-1")

    run(auth, 200)
    run(auth, 200)

    fake.refresh_token.assert_called_once_with("refresh-1")


def test_a_401_renews_the_token_and_retries_once():
    fake = flow(token("access-1"), token("access-2"))
    auth = RefreshTokenAuth(fake, "refresh-1")

    assert run(auth, 401, 200) == ["Bearer access-1", "Bearer access-2"]


def test_the_rotated_refresh_token_is_used_for_the_next_exchange():
    """Keycloak issues a new refresh token each time; holding the old one locks us out."""
    fake = flow(token("access-1", refresh="refresh-2"), token("access-2"))
    auth = RefreshTokenAuth(fake, "refresh-1")

    run(auth, 401, 200)

    assert [call.args[0] for call in fake.refresh_token.call_args_list] == [
        "refresh-1",
        "refresh-2",
    ]


def test_an_exchange_that_returns_no_refresh_token_keeps_the_one_it_has():
    fake = flow(token("access-1", refresh=None), token("access-2"))
    auth = RefreshTokenAuth(fake, "refresh-1")

    run(auth, 401, 200)

    assert [call.args[0] for call in fake.refresh_token.call_args_list] == [
        "refresh-1",
        "refresh-1",
    ]


def test_the_flow_is_pointed_at_the_environments_client():
    assert auth_code_flow("staging").client_id == "destiny-auth-client-staging"
    assert auth_code_flow("staging").redirect_uri == "http://localhost:8400/callback"


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch):
    for name in (
        "AZURE_CLIENT_ID",
        "MAPPER_DESTINY_APPLICATION_ID",
        "MAPPER_DESTINY_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_a_refresh_token_is_chosen_over_a_browser_login(monkeypatch):
    monkeypatch.setenv("MAPPER_DESTINY_REFRESH_TOKEN", "refresh-1")

    assert isinstance(_destiny_auth("staging"), RefreshTokenAuth)


def test_managed_identity_wins_over_a_stray_refresh_token(monkeypatch):
    """A deployed worker must not fall back to a developer's token."""
    monkeypatch.setenv("AZURE_CLIENT_ID", "client-id")
    monkeypatch.setenv("MAPPER_DESTINY_APPLICATION_ID", "app-id")
    monkeypatch.setenv("MAPPER_DESTINY_REFRESH_TOKEN", "refresh-1")

    assert not isinstance(_destiny_auth("staging"), RefreshTokenAuth)


def test_no_credentials_leaves_the_sdk_to_prompt():
    assert _destiny_auth("staging") is None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def loopback_server(port: int) -> HTTPServer:
    """A server bound the way the SDK binds its callback server."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"reached the callback")

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_the_relay_carries_a_published_port_to_the_loopback_callback():
    """A container publishes a port; the SDK only listens on localhost inside it."""
    target, listen = free_port(), free_port()
    server = loopback_server(target)
    try:
        start_relay(listen, target)
        response = httpx.get(f"http://127.0.0.1:{listen}/callback", timeout=5)
    finally:
        server.shutdown()

    assert response.text == "reached the callback"


def test_the_relay_waits_for_a_callback_server_that_is_not_up_yet():
    """It starts before the SDK binds, so an early redirect must not be refused."""
    target, listen = free_port(), free_port()
    start_relay(listen, target)
    server: list[HTTPServer] = []
    timer = threading.Timer(0.4, lambda: server.append(loopback_server(target)))
    timer.start()
    try:
        response = httpx.get(f"http://127.0.0.1:{listen}/callback", timeout=5)
    finally:
        timer.join()
        server[0].shutdown()

    assert response.text == "reached the callback"
