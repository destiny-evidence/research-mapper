import logging
import os

import dspy

logger = logging.getLogger(__name__)


def configure_dspy():
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
