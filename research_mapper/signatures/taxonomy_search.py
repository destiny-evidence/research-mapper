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


class GatherEvidenceFromConceptFilters(dspy.Signature):
    """
    Retrieve sources from the DESTINY repository using a preset set of concept filters.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The original user query for context."
    )
    filter_groups: list[ConceptFilterGroup] = dspy.InputField(
        desc="The concept filters that have been fixed for use, for context."
    )
    search_summary: str = dspy.OutputField(
        desc="Brief summary of what was retrieved and how it relates to the query."
    )
    stopping_reason: str = dspy.OutputField(
        desc="The reason for stopping the search, i.e. not including more results."
    )
