"""A DSPy engine that answers decision outputs with Azure OpenAI's Decisions API.

DSPy sends a structured decision request to any engine with
``supports_decision_requests = True``, instead of prompting a chat model to
write its own probabilities. This engine turns that request into one
``POST {base_url}/decisions`` call, shaped like Azure's documented curl
example, and hands the probabilities back. ``Predict`` then applies its
thresholds, cuts and weights as usual.

    lm = dspy.LM("gpt-6-luna", engine=DecisionsEngine(base_url, api_key))

The model sent to the API is the ``dspy.LM``'s, which DSPy puts on every
request. The engine reads no environment: ``config.get_decision_model`` builds
it from settings.

``Noul`` is sent as a ``predicate``, ``Choice`` as a ``choice`` and ``Score``
as a ``score``. The response shape follows the ``Decision`` type in the
``openai`` package (3.49): answers in question order, any of which can be a
refusal.
"""

import json
from typing import Any

import httpx
from dspy.lm15 import DataPart, Message, Request, Response, Usage
from dspy.utils.exceptions import (
    LMProviderError,
    LMRateLimitError,
    LMServerError,
    LMTimeoutError,
    LMTransportError,
)


PROVIDER = "azure-decisions"  # labels errors; not sent anywhere


class DecisionsEngine:
    """Completes DSPy decision requests against ``{base_url}/decisions``.

    DSPy owns retries and caching, so this makes one HTTP attempt per call.
    429s, 5xx, timeouts and network errors are raised as DSPy's retryable
    error types, and everything else as a non-retryable ``LMProviderError``.
    """

    supports_decision_requests = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # Accept the resource's /openai/v1 URL or the full /decisions endpoint.
        base_url = base_url.rstrip("/").removesuffix("/decisions")
        self.url = base_url + "/decisions"
        self._client = httpx.Client(
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def complete(self, request: Request) -> Response:
        questions = request.config.extensions["questions"]
        data = self._post(
            {
                "model": request.model,
                "input": _input_text(request),
                "questions": [_question(name, q) for name, q in questions.items()],
            },
            model=request.model,
        )
        answers = _answers(data, questions)
        usage = data.get("usage") or {}
        return Response(
            id=None,
            model=data.get("model") or request.model,
            message=Message(role="assistant", parts=(DataPart(value=answers),)),
            finish_reason="stop",
            usage=Usage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
            ),
            # DecisionAdapter reads answers from this key for every System One
            # engine, not only TypeSafe's.
            provider_data={"typesafe": {"answers": answers}},
        )

    def close(self) -> None:
        self._client.close()

    def _post(self, body: dict[str, Any], model: str) -> dict[str, Any]:
        errors: dict[str, Any] = {"model": model, "provider": PROVIDER}
        try:
            response = self._client.post(self.url, json=body)
        except httpx.TimeoutException as exc:
            raise LMTimeoutError(f"POST {self.url} timed out: {exc}", **errors) from exc
        except httpx.TransportError as exc:
            raise LMTransportError(f"POST {self.url} failed: {exc}", **errors) from exc

        status = response.status_code
        if status < 400:
            return response.json()
        message = f"POST {self.url} returned {status}: {response.text[:500]}"
        errors["status"] = status
        if status == 429:
            retry_after = response.headers.get("retry-after")
            raise LMRateLimitError(
                message,
                retry_after=float(retry_after)
                if retry_after and retry_after.isdigit()
                else None,
                **errors,
            )
        if status >= 500:
            raise LMServerError(message, **errors)
        raise LMProviderError(message, **errors)


def _input_text(request: Request) -> str:
    """The task and its inputs, as the single ``input`` string the API takes.

    DSPy puts the signature's instructions, input field descriptions, inputs
    and any demos in one structured user message.
    """
    parts = request.messages[0].parts
    if len(parts) != 1 or not isinstance(parts[0], DataPart):
        raise ValueError(
            "DecisionsEngine handles text-only inputs; images are not wired up yet."
        )
    state = parts[0].value
    if not isinstance(state, dict):
        raise ValueError(f"Unexpected decision request input: {state!r}")
    sections = [str(state.get("instructions") or "").strip()]
    if state.get("demos"):
        sections.append("Examples:\n" + json.dumps(state["demos"], ensure_ascii=False))
    sections.append(
        "Inputs:\n" + json.dumps(state.get("inputs", {}), ensure_ascii=False, indent=2)
    )
    return "\n\n".join(s for s in sections if s)


def _text(value: Any) -> str:
    """DSPy allows JSON instructions and criteria; the API takes text."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _question(name: str, question: dict[str, Any]) -> dict[str, Any]:
    """One DSPy question as a Decisions API question."""
    kind = question["type"]
    instructions = _text(question["instructions"])

    if kind == "noul":
        # A predicate has no options to describe, so the meanings from
        # Noul[(True, ...), (False, ...)] go in the instructions.
        criteria = question.get("criteria") or {}
        meanings = "; ".join(
            f"{k}: {_text(v)}" for k, v in criteria.items() if v is not None
        )
        if meanings:
            instructions = f"{instructions}\nTrue and false mean: {meanings}"
        return {"name": name, "type": "predicate", "instructions": instructions}

    if kind == "choice":
        return {
            "name": name,
            "type": "choice",
            "instructions": instructions,
            "choices": [
                {
                    "value": label,
                    **({"description": _text(desc)} if desc is not None else {}),
                }
                for label, desc in question["criteria"].items()
            ],
        }

    if kind == "score":
        # Labels are the level indices DSPy decodes; descriptions carry the rubric.
        return {
            "name": name,
            "type": "score",
            "instructions": instructions,
            "levels": [
                {"label": str(i), "description": _text(desc)}
                for i, desc in enumerate(question["criteria"])
            ],
        }

    raise ValueError(f"DecisionsEngine cannot send {kind!r} output {name!r}.")


def _answers(data: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
    """The API's answers, in the shape DSPy's decision decoder reads."""
    received = data.get("answers")
    if not isinstance(received, list) or len(received) != len(questions):
        raise LMProviderError(
            f"Unrecognised Decisions API response: {json.dumps(data)[:500]}",
            provider=PROVIDER,
        )
    answers: dict[str, Any] = {}
    for name, answer in zip(questions, received):
        kind = answer.get("type")
        if kind == "refusal":
            raise LMProviderError(
                f"Decisions API refused to answer {name!r}", provider=PROVIDER
            )
        if kind == "predicate":
            answers[name] = {"noul": answer["probability"]}
        elif kind == "choice":
            answers[name] = {
                "probabilities": {
                    str(p["value"]): p["probability"] for p in answer["probabilities"]
                },
                "confidence": answer["confidence"],
            }
        elif kind == "score":
            answers[name] = {
                "probabilities": {
                    p["label"]: p["probability"] for p in answer["probabilities"]
                },
                "confidence": answer["confidence"],
            }
        else:
            raise LMProviderError(
                f"Unknown answer type {kind!r} for {name!r}", provider=PROVIDER
            )
    return answers
