import dspy

from research_mapper.models.common import UserQuery
from research_mapper.models.taxonomy_search import Concept, ConceptFilterGroup


class TaxonomyConceptFiltersFromUserQuery(dspy.Signature):
    """Select concept filters from a vocabulary/taxonomy that narrows academic evidence/references relevant to the user's query."""

    user_query: UserQuery = dspy.InputField(desc="The user's original query/question.")
    taxonomy_concepts: list[Concept] = dspy.InputField(
        desc="The taxonomy's concepts to choose from."
    )
    filter_groups: list[ConceptFilterGroup] = dspy.OutputField(
        desc="The collection of concept filters to apply, grouped by scheme, with accompanying justifications."
    )
