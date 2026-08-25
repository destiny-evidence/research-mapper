"""Bearer-token authentication against Keycloak. Off unless configured."""

import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request, status

ALGORITHMS = ["RS256"]
REQUIRED_ROLE = "research_mapper"
LOCAL_PRINCIPAL = ("local", "local")
BEARER = {"WWW-Authenticate": "Bearer"}

Principal = tuple[str, str]


def settings() -> tuple[str, str] | None:
    """The issuer and client id to validate against."""
    issuer = os.environ.get("MAPPER_AUTH_ISSUER")
    client_id = os.environ.get("MAPPER_AUTH_CLIENT_ID")
    if issuer and client_id:
        return issuer.rstrip("/"), client_id
    return None


@lru_cache(maxsize=4)
def keys(issuer: str) -> jwt.PyJWKClient:
    """The signing keys for one issuer, cached across requests."""
    return jwt.PyJWKClient(f"{issuer}/protocol/openid-connect/certs")


def principal(request: Request) -> Principal:
    """The caller's (issuer, subject), or the one local user when auth is off."""
    configured = settings()
    if configured is None:
        return LOCAL_PRINCIPAL
    issuer, client_id = configured

    claims = _claims(_bearer(request), issuer, client_id)
    roles = claims.get("resource_access", {}).get(client_id, {}).get("roles", [])
    if REQUIRED_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"not a {REQUIRED_ROLE}")
    return claims["iss"], claims["sub"]


def _bearer(request: Request) -> str:
    """The token from an Authorization header, or a 401."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers=BEARER
        )
    return token


def _claims(token: str, issuer: str, client_id: str) -> dict:
    """Verified claims, or a HTTPException."""
    try:
        key = keys(issuer).get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"cannot reach {issuer}"
        ) from exc
    except jwt.PyJWKClientError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(exc), headers=BEARER
        ) from exc

    try:
        return jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(exc), headers=BEARER
        ) from exc
