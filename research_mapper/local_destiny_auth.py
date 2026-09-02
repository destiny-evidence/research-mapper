"""Local-development interactive DESTINY auth.

Generates a repository-scoped refresh token once and then uses that across the API/worker.
"""

import contextlib
import sys
import threading
from collections.abc import Generator

import httpx
from destiny_sdk.keycloak_auth import KeycloakAuthCodeFlow, TokenResponse

KEYCLOAK_URL = "https://auth.evidence-repository.org"
REALM = "destiny"
CALLBACK_PORT = 8400
REFRESH_TOKEN_VAR = "MAPPER_DESTINY_REFRESH_TOKEN"


def auth_code_flow(
    env: str, callback_port: int = CALLBACK_PORT
) -> KeycloakAuthCodeFlow:
    """The interactive login flow for one DESTINY environment."""
    return KeycloakAuthCodeFlow(
        keycloak_url=KEYCLOAK_URL,
        realm=REALM,
        client_id=f"destiny-auth-client-{env}",
        callback_port=callback_port,
    )


class RefreshTokenAuth(httpx.Auth):
    """Trades a refresh token for access tokens. Never opens a browser."""

    def __init__(self, flow: KeycloakAuthCodeFlow, refresh_token: str) -> None:
        self._flow = flow
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._lock = threading.Lock()

    def _token(self, stale: str | None = None) -> str:
        """The current access token, renewed if `stale` is still the current one."""
        with self._lock:
            if self._access_token is None or self._access_token == stale:
                token = self._flow.refresh_token(self._refresh_token)
                self._refresh_token = token.refresh_token or self._refresh_token
                self._access_token = token.access_token
            return self._access_token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Attach an access token, renewing it once if the request comes back 401."""
        attempted = self._token()
        request.headers["Authorization"] = f"Bearer {attempted}"
        response = yield request
        if response.status_code == httpx.codes.UNAUTHORIZED:
            request.headers["Authorization"] = f"Bearer {self._token(attempted)}"
            yield request


def login(env: str) -> TokenResponse:
    """Log in to DESTINY in a browser and return the tokens Keycloak issued."""
    flow = auth_code_flow(env)
    with contextlib.redirect_stdout(sys.stderr):
        return flow.authenticate()
