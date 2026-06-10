from .models import (
    LuceneQuery,
    UserQuery,
    Evidence,
    ScreeningCriterion,
    MappingDimension,
    DimensionSubTopic,
)

import dspy


class UserQueryToLuceneSearchQueries(dspy.Signature):
    "Generate search queries in Lucene syntax to search an academic repository with."

    original_query: UserQuery = dspy.InputField(
        desc="The user's original query/question."
    )
    search_queries: list[LuceneQuery] = dspy.OutputField(
        desc="A list of Lucence syntax-based search queries to search an evidence database with."
    )


class GatherEvidenceFromSearchQuery(dspy.Signature):
    """
    Retrieve sources from the DESTINY climate and health academic repository with a preset search query.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The original user query for context."
    )
    search_query: LuceneQuery = dspy.InputField(
        desc="The search query that has been fixed for use."
    )
    search_summary: str = dspy.OutputField(
        desc="Brief summary of what was retrieved and how it relates to the query."
    )
    stopping_reason: str = dspy.OutputField(
        desc="The reason for stopping the search, i.e. not including more results."
    )


class UserQueryToScreeningCriteria(dspy.Signature):
    """
    Generate a set of inclusion and exclusion criteria for evidence that could help answer a user's query.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The original user query for context."
    )
    screening_criteria: list[ScreeningCriterion] = dspy.OutputField(
        desc="A list of inclusion and exclusion criteria to screen evidence for."
    )


class ScreenEvidenceUsingCriteria(dspy.Signature):
    """
    Screen a piece of evidence using provided inclusion and exclusion criteria.
    """

    evidence: Evidence = dspy.InputField(
        desc="A potential piece of evidence to screen for relevance."
    )
    screening_criteria: list[ScreeningCriterion] = dspy.InputField(
        desc="A list of inclusion and exclusion criteria to abide by."
    )
    include: bool = dspy.OutputField(
        desc="Whether the piece of evidence should be included or not."
    )


class EvidenceMappingDimensionsFromQuery(dspy.Signature):
    """
    Suggest 3 dimensions, e.g. 2 dimensions and 1 facet, to map academic evidence across.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The user's original query that initiated the evidence map."
    )
    dimensions: tuple[MappingDimension, MappingDimension, MappingDimension] = (
        dspy.OutputField(desc="The dimensions to map the evidence data against.")
    )


class SubtopicFromEvidenceMappingDimension(dspy.Signature):
    """
    Suggest a collection of sub-topics/dimensions for a given evidence mapping dimension.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The user's original query that initiated the evidence map."
    )
    other_dimensions: list[MappingDimension] = dspy.InputField(
        desc="The other top-level evidence mapping dimensions that will be used, for context."
    )
    dimension: MappingDimension = dspy.InputField(
        desc="The evidence mapping dimension to generate sub-topics/dimensions for."
    )
    subtopics: list[DimensionSubTopic] = dspy.OutputField(
        desc="The collection of sub-topics/dimensions for the given evidence mapping dimension."
    )
