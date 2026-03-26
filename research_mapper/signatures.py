from .models import LuceneQuery, UserQuery, Evidence

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
    Retrieve sources from the DESTINY climate and health academic repository using a search query.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The original user query for context."
    )
    search_query: LuceneQuery = dspy.InputField(desc="The search query to use.")
    evidence: list[Evidence] = dspy.OutputField(
        desc="A list of relevant Evidence born from the search."
    )
