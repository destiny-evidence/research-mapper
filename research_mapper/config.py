import logging
import os
from functools import lru_cache

import dspy
from destiny_sdk.client import OAuthClient

logger = logging.getLogger(__name__)


def configure_dspy() -> None:
    """
    Configures the LLM provider for DSPy from environment variables.
    :return: Nothing.
    """
    model = os.environ["LLM_MODEL"]
    api_base = os.environ["OPENAI_API_BASE"]
    logger.info("Configuring LLM: model=%s, api_base=%s", model, api_base)
    lm = dspy.LM(
        model=model,
        api_base=api_base,
        api_key=os.environ["OPENAI_API_KEY"],
    )
    logger.debug("Running LLM sanity check")
    result = lm("Say: 'hello world'", temperature=0.0)
    assert "hello world" in result, result
    dspy.configure(lm=lm)
    logger.info("DSPy configured successfully!")


@lru_cache(maxsize=1)
def get_destiny_client() -> OAuthClient:
    logger.info("Initialising Destiny OAuth client")
    client = OAuthClient(
        base_url=os.environ.get("DESTINY_BASE_URL"),
        env=os.environ.get("DESTINY_ENV", "production"),
    )
    logger.debug("Triggering eagerly OAuth token fetch via health check")
    client.get_client().get("/v1/system/healthcheck/")
    logger.info("Destiny client authenticated and healthy")
    return client
