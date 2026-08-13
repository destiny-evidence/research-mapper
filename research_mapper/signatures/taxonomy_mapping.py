from typing import Literal

import dspy

from research_mapper.models.common import UserQuery


def taxonomy_scheme_dimensions_signature_builder(
    available_schemes: list[str],
) -> type[dspy.Signature]:
    """
    Dynamically builds a dspy.Signature for selecting 3 taxonomy schemes to map evidence
    across, constraining each output field to `available_schemes` via a dynamically-built
    typing.Literal — the same hallucination-resistant technique already used by
    `mapping_along_dimensions_signature_builder` and the taxonomy concept-filter
    generator's local_ref indirection.
    :param available_schemes: the candidate scheme names the LLM may choose from —
        already restricted (by the caller) to schemes represented in the evidence being
        mapped, not every scheme the taxonomy happens to define.
    :return: a dynamically-built TaxonomySchemeDimensions signature
    :raises ValueError: if fewer than 3 schemes are available to choose from
    """
    if len(available_schemes) < 3:
        msg = f"Need at least 3 available schemes, got {len(available_schemes)}."
        raise ValueError(msg)

    SchemeLiteral = Literal[tuple(available_schemes)]
    docstring = (
        "Suggest 3 taxonomy schemes, from the available candidates, worth mapping "
        "academic evidence across."
    )
    fields = {
        "original_query": dspy.InputField(
            desc="The user's original query that initiated the evidence map."
        ),
        "scheme1": dspy.OutputField(
            desc="The first taxonomy scheme to map the evidence data against."
        ),
        "scheme2": dspy.OutputField(
            desc="The second taxonomy scheme to map the evidence data against."
        ),
        "scheme3": dspy.OutputField(
            desc="The third taxonomy scheme to map the evidence data against."
        ),
    }
    annotations = {
        "original_query": UserQuery,
        "scheme1": SchemeLiteral,
        "scheme2": SchemeLiteral,
        "scheme3": SchemeLiteral,
    }
    return type(
        "TaxonomySchemeDimensions",
        (dspy.Signature,),
        {**fields, "__annotations__": annotations, "__doc__": docstring},
    )
