from research_mapper.engine.models import Decision


class InvalidAnswer(ValueError):
    """An answer does not satisfy the decision it responds to."""


def validate_answer(decision: Decision, answer: list[dict]) -> None:
    """Check an answer against its decision's options and constraints."""
    if not isinstance(answer, list) or not all(
        isinstance(item, dict) for item in answer
    ):
        msg = "an answer is a list of records"
        raise InvalidAnswer(msg)

    minimum = decision.constraints.get("min", 0)
    maximum = decision.constraints.get("max")
    if len(answer) < minimum:
        msg = f"pick at least {minimum}"
        raise InvalidAnswer(msg)
    if maximum is not None and len(answer) > maximum:
        msg = f"pick at most {maximum}"
        raise InvalidAnswer(msg)

    exclusive = decision.constraints.get("exclusive", [])
    if len(answer) > 1 and any(item in exclusive for item in answer):
        msg = "that option has to be chosen on its own"
        raise InvalidAnswer(msg)

    if not decision.constraints.get("allow_new"):
        offered = [option["value"] for option in decision.options]
        if unoffered := [item for item in answer if item not in offered]:
            msg = f"{len(unoffered)} of {len(answer)} records were not offered"
            raise InvalidAnswer(msg)
