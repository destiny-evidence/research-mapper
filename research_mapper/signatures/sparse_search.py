import dspy

from research_mapper.models import UserQuery, LuceneQuery


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
