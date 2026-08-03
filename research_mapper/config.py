import logging
import os
from functools import lru_cache
from pathlib import Path

import dspy
from destiny_sdk.client import OAuthClient
from dotenv import load_dotenv, find_dotenv

logger = logging.getLogger(__name__)


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
    assert result and result[0], result
    dspy.configure(lm=lm)
    logger.info("DSPy configured successfully!")


@lru_cache(maxsize=1)
def get_destiny_client() -> OAuthClient:
    logger.info("Initialising Destiny OAuth client")
    client = OAuthClient(
        base_url=os.environ.get("MAPPER_DESTINY_BASE_URL"),
        env=os.environ.get("MAPPER_DESTINY_ENV", "production"),
    )
    logger.debug("Triggering eagerly OAuth token fetch via health check")
    client.get_client().get("/v1/system/healthcheck/")
    logger.info("Destiny client authenticated and healthy")
    return client
