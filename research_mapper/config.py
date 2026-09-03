import logging
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import dspy
import httpx
from destiny_sdk.client import OAuthClient, OAuthMiddleware
from dotenv import load_dotenv, find_dotenv

from research_mapper import local_destiny_auth
from research_mapper.db.session import db_manager

logger = logging.getLogger(__name__)

HEALTHCHECK_TIMEOUT = 30.0


class NoDestinyCredential(RuntimeError):
    """Nothing is configured to authenticate to DESTINY, and nobody can be asked."""


def _global_env_path() -> Path:
    if os.name == "nt":
        config_home = os.environ.get("APPDATA", "~/AppData/Roaming")
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(config_home).expanduser() / "research-mapper" / ".env"


def load_environment(env_file: str | None = None) -> None:
    """
    Loads configuration from environment variables and .env files.

    Precedence (highest to lowest): variables already exported in the shell,
    an explicit ``env_file``, ``./.env`` (or a parent directory's), and
    finally a machine-wide fallback (``$XDG_CONFIG_HOME/research-mapper/.env``,
    or ``%APPDATA%\\research-mapper\\.env`` on Windows). Already-set
    variables are never overridden, so higher-precedence sources just need
    to be loaded first.
    :param env_file: optional explicit path to a .env file.
    :return: Nothing.
    """
    if env_file:
        path = Path(env_file)
        if not path.is_file():
            msg = f"--env-file {env_file} does not exist"
            raise FileNotFoundError(msg)
        load_dotenv(path)
    # usecwd=True: without it, load_dotenv() searches upward from the *calling
    # file's* location rather than the user's actual working directory — for an
    # installed console script, that's somewhere in site-packages, never the
    # user's cwd, so their local .env would silently never be found.
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(_global_env_path())


def configure_dspy() -> None:
    """
    Configures the LLM provider for DSPy from environment variables.
    :return: Nothing.
    """
    model = os.environ["MAPPER_LLM_MODEL"]
    api_base = os.environ["MAPPER_LLM_BASE_URL"]
    logger.info("Configuring LLM: model=%s, api_base=%s", model, api_base)
    lm = dspy.LM(
        model=model,
        api_base=api_base,
        api_key=os.environ["MAPPER_LLM_API_KEY"],
    )
    logger.debug("Running LLM sanity check")
    result = lm("Say: 'hello world'", temperature=0.0)
    if not result or not result[0]:
        logger.warning("LLM sanity check returned nothing: %s", result)
    dspy.configure(lm=lm)
    logger.info("DSPy configured successfully!")


@contextmanager
def reroll(seed: int) -> Generator[None]:
    """Ask the LLM again without being served its cached answer.

    rollout_id varies the cache key, and DSPy ignores it at zero temperature.
    """
    lm = dspy.settings.lm
    if not seed or lm is None:
        yield
        return
    temperature = lm.kwargs.get("temperature") or 1
    with dspy.context(lm=lm.copy(rollout_id=seed, temperature=temperature)):
        yield


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


def init_database() -> None:
    """Initializes the database session manager from environment variables."""
    db_manager.init()


def close_database() -> None:
    """Closes the database session manager."""
    db_manager.close()
