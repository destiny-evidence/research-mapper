import dspy

from research_mapper.models.common import UserQuery
from research_mapper.models.mapping import (
    DimensionSubTopic,
    MappingDimensionWithSubTopics,
)
from research_mapper.models.taxonomy_search import IndexedVocab
from research_mapper.signatures.taxonomy_mapping import (
    taxonomy_scheme_dimensions_signature_builder,
)


class TaxonomySchemeDimensionGenerator(dspy.Module):
    """
    Selects 3 taxonomy schemes to map evidence across, from a restricted candidate
    list, then builds each as a MappingDimensionWithSubTopics directly from the
    taxonomy's own concepts — no separate subtopic-curation LLM call, unlike the
    free-form dimension/subtopic path.
    """

    def forward(
        self,
        user_query: UserQuery,
        indexed_vocab: IndexedVocab,
        available_schemes: list[str],
    ) -> dspy.Prediction:
        """
        Selects 3 schemes and builds their dimensions.
        :param user_query: the user's original query, for context
        :param indexed_vocab: the taxonomy's indexed concepts, to pull subtopics from
        :param available_schemes: the candidate scheme names the LLM may choose from
        :return: a Prediction wrapping dimension1, dimension2, dimension3 (each a fully
            built MappingDimensionWithSubTopics) and reasoning
        :raises RuntimeError: if fewer than 3 schemes were available, or the LLM picked
            the same scheme more than once
        """
        try:
            TaxonomySchemeDimensions = taxonomy_scheme_dimensions_signature_builder(
                available_schemes
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

        select_schemes = dspy.ChainOfThought(TaxonomySchemeDimensions)
        prediction = select_schemes(original_query=user_query)
        chosen = (prediction.scheme1, prediction.scheme2, prediction.scheme3)
        if len(set(chosen)) != len(chosen):
            msg = f"The same scheme was picked more than once: {chosen}."
            raise RuntimeError(msg)

        dimensions = tuple(
            self._build_dimension(scheme_name, indexed_vocab) for scheme_name in chosen
        )
        return dspy.Prediction(
            dimension1=dimensions[0],
            dimension2=dimensions[1],
            dimension3=dimensions[2],
            reasoning=prediction.reasoning,
        )

    @staticmethod
    def _build_dimension(
        scheme_name: str, indexed_vocab: IndexedVocab
    ) -> MappingDimensionWithSubTopics:
        """
        Builds a scheme's MappingDimensionWithSubTopics directly from the taxonomy —
        every concept in the scheme becomes a subtopic, as-is, with no LLM curation.
        :param scheme_name: the chosen scheme's name
        :param indexed_vocab: the taxonomy's indexed concepts
        :return: the scheme, built as a MappingDimensionWithSubTopics
        """
        return MappingDimensionWithSubTopics(
            name=scheme_name,
            description=f"Taxonomy scheme: {scheme_name}",
            subtopics=[
                DimensionSubTopic(name=concept.label, description=concept.detail or "")
                for concept in indexed_vocab.concepts
                if concept.scheme == scheme_name
            ],
        )
