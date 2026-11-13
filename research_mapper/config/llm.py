import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

import dspy
from dspy.experimental import Noul

from research_mapper.decisions_engine import DecisionsEngine

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 120.0
DECISION_TIMEOUT_SECONDS = 30.0
DECISION_VARS = (
    "MAPPER_DECISION_MODEL",
    "MAPPER_DECISION_BASE_URL",
    "MAPPER_DECISION_API_KEY",
)


def _chat_lm(cache: bool = True) -> dspy.LM:
    """The chat model, from the MAPPER_LLM_* settings every part of the app needs."""
    model = os.environ["MAPPER_LLM_MODEL"]
    api_base = os.environ["MAPPER_LLM_BASE_URL"]
    logger.info("Configuring LLM: model=%s, api_base=%s", model, api_base)
    return dspy.LM(
        model=model,
        api_base=api_base,
        api_key=os.environ["MAPPER_LLM_API_KEY"],
        timeout=float(os.environ.get("MAPPER_LLM_TIMEOUT") or LLM_TIMEOUT_SECONDS),
        cache=cache,
    )


def configure_dspy() -> None:
    """
    Configures the LLM provider for DSPy from environment variables.
    :return: Nothing.
    """
    lm = _chat_lm()
    logger.debug("Running LLM sanity check")
    result = lm("Say: 'hello world'")
    if not result or not result[0]:
        logger.warning("LLM sanity check returned nothing: %s", result)
    dspy.configure(lm=lm)
    logger.info("DSPy configured successfully!")

    logger.debug("Running decision model sanity check")
    _check_decision_model(get_decision_model())


@lru_cache(maxsize=2)
def get_decision_model(cache: bool = True) -> dspy.LM:
    """
    The LM that answers decision outputs, kept apart from the global chat model.

    Modules with decision outputs bind it themselves. The decision settings are
    all-or-nothing: with MAPPER_DECISION_MODEL, MAPPER_DECISION_BASE_URL and
    MAPPER_DECISION_API_KEY all set, decisions go to that model's Decisions
    endpoint. Otherwise they fall back to the chat model, which DSPy asks to
    report its own probabilities, rather than mixing one setting with another's.
    :param cache: whether DSPy caches answers. ReAnchor needs this on.
    :return: the dedicated decision model, or the chat model.
    """
    settings = {var: os.environ.get(var) for var in DECISION_VARS}
    if not all(settings.values()):
        missing = [var for var, value in settings.items() if not value]
        if len(missing) < len(DECISION_VARS):
            logger.warning(
                "Ignoring partial decision model settings, missing %s", missing
            )
        logger.warning(
            "No decision model configured: decisions use the chat model, "
            "whose probabilities are self-reported"
        )
        return _chat_lm(cache=cache)

    model = os.environ["MAPPER_DECISION_MODEL"]
    base_url = os.environ["MAPPER_DECISION_BASE_URL"]
    logger.info("Configuring decision model: model=%s, base_url=%s", model, base_url)
    engine = DecisionsEngine(
        base_url=base_url,
        api_key=os.environ["MAPPER_DECISION_API_KEY"],
        timeout=float(
            os.environ.get("MAPPER_DECISION_TIMEOUT") or DECISION_TIMEOUT_SECONDS
        ),
    )
    return dspy.LM(model, engine=engine, cache=cache)


class _DecisionCheck(dspy.Signature):
    """Answer the question about the text."""

    text: str = dspy.InputField()
    greeting: Noul = dspy.OutputField(desc="Is the text a greeting?")


def _check_decision_model(lm: dspy.LM) -> None:
    """Fail at startup, not on the first screening batch, if the endpoint is wrong."""
    check = dspy.Predict(_DecisionCheck)
    check.set_lm(lm)
    check(text="hello world")


@contextmanager
def reroll(seed: int) -> Generator[None]:
    """Ask the LLM again without being served its cached answer.

    rollout_id varies the cache key, and DSPy ignores it at zero temperature.

    Only the global chat model is rerolled. Predictors bound to their own LM,
    such as the decision model, keep it, and decisions have nothing to resample:
    the decision model returns probabilities, so the threshold is what to vary.
    """
    lm = dspy.settings.lm
    if not seed or lm is None:
        yield
        return
    temperature = lm.kwargs.get("temperature") or 1
    with dspy.context(lm=lm.copy(rollout_id=seed, temperature=temperature)):
        yield
