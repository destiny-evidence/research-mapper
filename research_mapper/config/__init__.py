"""Application configuration, read from the environment.

environment   loading .env files
llm           the chat model and the decision model
destiny       the DESTINY repository client
database      the database session manager
"""

from research_mapper.config.database import close_database, init_database
from research_mapper.config.destiny import (
    HEALTHCHECK_TIMEOUT,
    NoDestinyCredential,
    get_destiny_client,
    init_destiny_client,
)
from research_mapper.config.environment import load_environment
from research_mapper.config.llm import (
    LLM_TIMEOUT_SECONDS,
    configure_dspy,
    get_decision_model,
    is_dedicated_decision_model,
    reroll,
)

__all__ = [
    "HEALTHCHECK_TIMEOUT",
    "LLM_TIMEOUT_SECONDS",
    "NoDestinyCredential",
    "close_database",
    "configure_dspy",
    "get_decision_model",
    "get_destiny_client",
    "init_database",
    "init_destiny_client",
    "is_dedicated_decision_model",
    "load_environment",
    "reroll",
]
