import logging
import os
import sys
from functools import lru_cache

import httpx
from destiny_sdk.client import OAuthMiddleware, OAuthClient

from research_mapper import local_destiny_auth

logger = logging.getLogger(__name__)

HEALTHCHECK_TIMEOUT = 30.0


class NoDestinyCredential(RuntimeError):
    """Nothing is configured to authenticate to DESTINY, and nobody can be asked."""


def _destiny_auth(env: str) -> httpx.Auth | None:
    """How to authenticate to DESTINY, or None to let the SDK prompt in a browser."""
    client_id = os.environ.get("AZURE_CLIENT_ID")
    application_id = os.environ.get("MAPPER_DESTINY_APPLICATION_ID")
    if client_id and application_id:
        logger.info("Authenticating to Destiny with managed identity")
        return OAuthMiddleware(
            azure_client_id=client_id,
            azure_application_id=application_id,
            use_managed_identity=True,
        )

    refresh_token = os.environ.get(local_destiny_auth.REFRESH_TOKEN_VAR)
    if refresh_token:
        logger.info("Authenticating to Destiny with a stored refresh token")
        return local_destiny_auth.RefreshTokenAuth(
            local_destiny_auth.auth_code_flow(env), refresh_token
        )
    return None


@lru_cache(maxsize=1)
def get_destiny_client() -> OAuthClient:
    """
    Builds an authenticated DESTINY repository client, eagerly triggering the
    OAuth handshake now rather than deferring it to the first search/lookup —
    a bad credential or unreachable DESTINY instance should fail loudly at
    startup, not silently wait to surface on a user's first request.
    """
    env = os.environ.get("MAPPER_DESTINY_ENV", "production")
    auth = _destiny_auth(env)

    interactive = sys.stdin.isatty()
    if auth is None and not interactive:
        msg = (
            "No DESTINY credential and no terminal to log in from. Set "
            f"{local_destiny_auth.REFRESH_TOKEN_VAR} (run "
            "`uv run python -m research_mapper login`), or AZURE_CLIENT_ID and "
            "MAPPER_DESTINY_APPLICATION_ID to use a managed identity."
        )
        raise NoDestinyCredential(msg)

    client = OAuthClient(auth=auth, env=env)
    logger.debug("Triggering eagerly OAuth token fetch via health check")
    timeout = httpx.USE_CLIENT_DEFAULT if auth is None else HEALTHCHECK_TIMEOUT
    client.get_client().get("/v1/system/healthcheck/", timeout=timeout)
    logger.info("Destiny client authenticated and healthy")
    return client


def init_destiny_client() -> None:
    """Eagerly authenticate to DESTINY."""
    get_destiny_client()
