from itertools import chain

import dspy

from research_mapper import taxonomy
from research_mapper.concept_search import retrieve_evidence_by_concepts
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.mapping import (
    EvidenceMap,
    MappedEvidence,
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.models.screening import ScreeningCriterion
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.modules.screening import CriteriaGenerator, EvidenceScreener
from research_mapper.modules.sparse_search import (
    EvidenceRetriever,
    SparseQueryGenerator,
)
from research_mapper.modules.mapping import (
    DimensionGenerator,
    EvidenceMapper,
    SubtopicGenerator,
)
from research_mapper.modules.taxonomy_search import TaxonomyConceptFilterGenerator
from research_mapper.ui.tui import TerminalUI

MAX_CONCURRENCY = 8


class ResearchMappingOrchestrator:
    """
    The application layer: drives the atomic search, screening, and mapping modules, streaming
    their progress and requesting human review between steps, to search, screen, and map
    evidence/research for a user's query.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.tui = tui
        self.search_query_generator = SparseQueryGenerator()
        self.evidence_retriever = EvidenceRetriever()
        self.concept_filter_generator = TaxonomyConceptFilterGenerator(ui=tui)
        self.criteria_generator = CriteriaGenerator()
        self.evidence_screener = EvidenceScreener()
        self.dimension_generator = DimensionGenerator()
        self.subtopic_generator = SubtopicGenerator()
        self.evidence_mapper = EvidenceMapper()

    def run(self, user_query: UserQuery) -> EvidenceMap:
        """
        Gathers, screens, and maps evidence for relevance to the user's query.
        :param user_query: the user query to map research for
        :return: an EvidenceMap of the screened, mapped evidence
        """
        evidence = self._gather_evidence(user_query)
        filtered_evidence = self._screen_evidence(user_query, evidence)
        return self._map_evidence(user_query, filtered_evidence)

    def _gather_evidence(self, user_query: UserQuery) -> list[Evidence]:
        """
        Generates search queries, validates them by the user, and retrieves evidence for each.
        :param user_query: the user query to gather evidence for
        :return: a collection of potentially relevant evidence
        """
        search_queries = self._generate_search_queries(user_query)
        search_queries = self._filter_search_queries(search_queries)
        evidence = self._retrieve_evidence(user_query, search_queries)
        if self.tui:
            self.tui.print_info(
                f"{len(evidence)} pieces of evidence retrieved. Moving onto screening."
            )
        return evidence

    def _generate_search_queries(self, user_query: UserQuery) -> list[LuceneQuery]:
        """
        Generates a set of candidate Lucene queries to search the DESTINY repository with.
        :param user_query: the user's query to generate search queries for
        :return: a collection of Lucene search queries
        """
        if self.tui:
            prediction = self.tui.run_with_status(
                self.search_query_generator,
                "Search queries",
                status="Generating suggested search queries...",
                user_query=user_query,
            )
        else:
            prediction = self.search_query_generator(user_query=user_query)
        return prediction.search_queries

    def _filter_search_queries(
        self, search_queries: list[LuceneQuery]
    ) -> list[LuceneQuery]:
        """
        Filters suggested search queries via the user when a UI is available. Accepts all if not.
        :param search_queries: the suggested search queries to be filtered
        :return: the filtered search queries
        """
        if self.tui is None:
            return search_queries
        return self.tui.select_from_list(
            search_queries, title="Suggested search queries"
        )

    def _retrieve_evidence(
        self, user_query: UserQuery, search_queries: list[LuceneQuery]
    ) -> list[Evidence]:
        """
        Dispatches subagents for each search query to retrieve evidence from the DESTINY
        repository, in parallel.
        :param user_query: the original user query, for context
        :param search_queries: the search queries to retrieve evidence for
        :return: a set of unique Evidence objects
        """
        if self.tui:
            self.tui.print_info(
                f"Retrieving evidence for {len(search_queries)} search quer"
                f"{'y' if len(search_queries) == 1 else 'ies'}..."
            )
        examples = [
            dspy.Example(user_query=user_query, search_query=search_query).with_inputs(
                "user_query", "search_query"
            )
            for search_query in search_queries
        ]
        results = self.evidence_retriever.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            self.tui.print_reasoning_batch(
                [str(q) for q in search_queries], [p.reasoning for p in results]
            )
        return list(
            set(chain.from_iterable(prediction.evidence for prediction in results))
        )

    def _generate_concept_filters(self, user_query: UserQuery) -> list[str | list[str]]:
        """
        Fetches the HPV taxonomy, generates concept filters relevant to the user's query, and
        resolves them to the concept IRIs the DESTINY search API expects.
        :param user_query: the user's original query to generate concept filters for
        :return: concept IRI filters, AND'd across entries and OR'd within an entry
        """
        vocab = taxonomy.get_taxonomy(taxonomy.RepoCommunity.HPV)
        indexed = taxonomy.build_concept_index(vocab)
        if self.tui:
            prediction = self.tui.run_with_status(
                self.concept_filter_generator,
                "Concept filters",
                status="Generating suggested concept filters...",
                user_query=user_query,
                taxonomy_concepts=indexed.concepts,
            )
        else:
            prediction = self.concept_filter_generator(
                user_query=user_query, taxonomy_concepts=indexed.concepts
            )
        return [
            indexed.resolve(group.concept_local_refs)
            for group in prediction.filter_groups
        ]

    def _gather_evidence_by_concepts(self, user_query: UserQuery) -> list[Evidence]:
        """
        Generates and applies concept filters to retrieve evidence directly, without going
        through Lucene search. Not yet wired into `run()` — a future mode-selection step
        will decide when to call this instead of (or alongside) `_gather_evidence`.
        :param user_query: the user query to gather concept-filtered evidence for
        :return: the matching evidence
        """
        concept_filters = self._generate_concept_filters(user_query)
        evidence = retrieve_evidence_by_concepts(
            taxonomy.RepoCommunity.HPV, concept_filters
        )
        if self.tui:
            self.tui.print_info(
                f"{len(evidence)} pieces of evidence retrieved via concept filters."
            )
        return evidence

    def _screen_evidence(
        self, user_query: UserQuery, evidence: list[Evidence]
    ) -> list[Evidence]:
        """
        Generates screening criteria, validates them by the user, and screens the given evidence
        against them.
        :param user_query: the user query to screen evidence for
        :param evidence: evidence to screen for relevance
        :return: a collection of screened evidence
        """
        screening_criteria = self._generate_screening_criteria(user_query)
        screening_criteria = self._filter_screening_criteria(screening_criteria)
        filtered_evidence = self._run_screening(screening_criteria, evidence)
        if self.tui:
            self.tui.print_info(
                f"{len(evidence) - len(filtered_evidence)} piece(s) of evidence removed during screening. {len(filtered_evidence)} piece(s) of evidence remaining."
            )
        return filtered_evidence

    def _generate_screening_criteria(
        self, user_query: UserQuery
    ) -> list[ScreeningCriterion]:
        """
        Generates a set of inclusion and exclusion screening criteria.
        :param user_query: the original user's query to generate screening criteria for
        :return: a list of ScreeningCriterion objects to consider
        """
        if self.tui:
            prediction = self.tui.run_with_status(
                self.criteria_generator,
                "Screening criteria",
                status="Generating suggested screening criteria...",
                user_query=user_query,
            )
        else:
            prediction = self.criteria_generator(user_query=user_query)
        return prediction.screening_criteria

    def _filter_screening_criteria(
        self, screening_criteria: list[ScreeningCriterion]
    ) -> list[ScreeningCriterion]:
        """
        Filters suggested screening criteria via the user when a UI is available. Accepts all
        criteria if not.
        :param screening_criteria: the suggested screening criteria to be filtered
        :return: a list of filtered screening criteria
        """
        if self.tui is None:
            return screening_criteria
        return self.tui.select_from_list(
            screening_criteria, title="Suggested screening criteria"
        )

    def _run_screening(
        self,
        screening_criteria: list[ScreeningCriterion],
        evidence: list[Evidence],
    ) -> list[Evidence]:
        """
        Screens each piece of evidence against the given screening criteria, in parallel.
        :param screening_criteria: the screening criteria to screen evidence against
        :param evidence: the Evidence objects to be screened
        :return: the collection of evidence to include
        """
        if self.tui:
            self.tui.print_info(f"Screening {len(evidence)} piece(s) of evidence...")
        examples = [
            dspy.Example(
                evidence=piece_of_evidence, screening_criteria=screening_criteria
            ).with_inputs("evidence", "screening_criteria")
            for piece_of_evidence in evidence
        ]
        results = self.evidence_screener.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            self.tui.print_reasoning_batch(
                [str(e) for e in evidence], [p.reasoning for p in results]
            )
        return [
            piece_of_evidence
            for piece_of_evidence, prediction in zip(evidence, results)
            if prediction.include
        ]

    def _map_evidence(
        self, user_query: UserQuery, filtered_evidence: list[Evidence]
    ) -> EvidenceMap:
        """
        Generates mapping dimensions and their subtopics, validates them by the user, and maps
        each piece of evidence to a coordinate across those dimensions.
        :param user_query: the user query the evidence is being mapped for
        :param filtered_evidence: the screened evidence to map
        :return: an EvidenceMap of the screened evidence
        """
        suggested_dimensions = self._generate_suggested_dimensions(user_query)
        finalised_dimensions = self._validate_dimensions(suggested_dimensions)
        suggested_subtopics = self._generate_dimension_subtopics(
            user_query, finalised_dimensions
        )
        final_dims_with_subtopics = self._validate_dimension_subtopics(
            suggested_subtopics
        )
        mapping = self._generate_evidence_map(
            user_query, final_dims_with_subtopics, filtered_evidence
        )
        return EvidenceMap(
            mapped_evidence=mapping, dimensions=final_dims_with_subtopics
        )

    def _generate_suggested_dimensions(
        self, user_query: UserQuery
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
        """
        Generates 3 suggested dimensions to map evidence across for a user's query.
        :param user_query: the user's original query to generate mapping dimensions for
        :return: the 3 suggested mapping dimensions
        """
        if self.tui:
            prediction = self.tui.run_with_status(
                self.dimension_generator,
                "Mapping dimensions",
                status="Generating suggested mapping dimensions...",
                user_query=user_query,
            )
        else:
            prediction = self.dimension_generator(user_query=user_query)
        return (prediction.dimension1, prediction.dimension2, prediction.dimension3)

    def _validate_dimensions(
        self, dimensions: tuple[MappingDimension, MappingDimension, MappingDimension]
    ) -> tuple[MappingDimension, MappingDimension, MappingDimension]:
        """
        Validates suggested mapping dimensions via the user when a UI is available. Accepts them
        all if not.
        :param dimensions: the suggested mapping dimensions to be validated
        :return: the finalised mapping dimensions
        """
        if self.tui is None:
            return dimensions
        finalised = self.tui.confirm_or_replace(
            dimensions, title="Suggested mapping dimensions", noun="dimensions"
        )
        return tuple(finalised)

    def _generate_dimension_subtopics(
        self,
        user_query: UserQuery,
        dimensions: tuple[MappingDimension, MappingDimension, MappingDimension],
    ) -> tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]:
        """
        Generates suggested subtopics for each mapping dimension, in parallel.
        :param user_query: the user's original query for context
        :param dimensions: the mapping dimensions to generate subtopics for
        :return: the mapping dimensions, each upgraded with their suggested subtopics
        """
        if self.tui:
            self.tui.print_info("Generating suggested subtopics for each dimension...")
        examples = [
            dspy.Example(
                user_query=user_query,
                dimension=dim,
                other_dimensions=list(dimensions[:i] + dimensions[i + 1 :]),
            ).with_inputs("user_query", "dimension", "other_dimensions")
            for i, dim in enumerate(dimensions)
        ]
        results = self.subtopic_generator.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            self.tui.print_reasoning_batch(
                [str(d) for d in dimensions], [p.reasoning for p in results]
            )
        return tuple(
            MappingDimensionWithSubTopics(
                **mapping_dim.model_dump(), subtopics=prediction.subtopics
            )
            for mapping_dim, prediction in zip(dimensions, results)
        )

    def _validate_dimension_subtopics(
        self,
        dimensions: tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
    ) -> tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]:
        """
        Validates suggested dimension subtopics via the user when a UI is available. Accepts them
        all if not. Re-prompts for a dimension if the user drops all of its subtopics, since each
        dimension must retain at least one.
        :param dimensions: the mapping dimensions with suggested subtopics to be validated
        :return: the mapping dimensions with finalised subtopics
        """
        if self.tui is None:
            return dimensions
        finalised_dimensions = tuple()
        for dim in dimensions:
            while True:
                finalised_subtopics = self.tui.confirm_or_replace(
                    dim.subtopics,
                    title=f"Suggested subtopics for '{dim.name}' dimension",
                    noun="subtopics",
                    allow_drop=True,
                )
                if finalised_subtopics:
                    break
                self.tui.print_info(
                    f"[red]'{dim.name}' must have at least one subtopic — try again.[/red]"
                )
            finalised_dimensions += (
                MappingDimensionWithSubTopics(
                    **dim.model_dump(exclude={"subtopics"}),
                    subtopics=finalised_subtopics,
                ),
            )
        return finalised_dimensions

    def _generate_evidence_map(
        self,
        user_query: UserQuery,
        dimensions: tuple[
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
            MappingDimensionWithSubTopics,
        ],
        evidence: list[Evidence],
    ) -> list[MappedEvidence]:
        """
        Maps each piece of evidence to a coordinate across the provided dimensions and their
        subtopics, in parallel.
        :param user_query: the user's original query for context
        :param dimensions: the finalised mapping dimensions, each with their finalised subtopics
        :param evidence: the Evidence objects to be mapped
        :return: the collection of MappedEvidence objects
        """
        if self.tui:
            self.tui.print_info(
                f"Mapping {len(evidence)} piece(s) of evidence across dimensions..."
            )
        examples = [
            dspy.Example(
                user_query=user_query, evidence=piece_of_evidence, dimensions=dimensions
            ).with_inputs("user_query", "evidence", "dimensions")
            for piece_of_evidence in evidence
        ]
        results = self.evidence_mapper.batch(examples, num_threads=MAX_CONCURRENCY)
        if self.tui:
            self.tui.print_reasoning_batch(
                [str(e) for e in evidence], [p.reasoning for p in results]
            )
        dimension_names = [dim.name for dim in dimensions]
        subtopic_fields = (
            "dimension1_subtopic",
            "dimension2_subtopic",
            "dimension3_subtopic",
        )
        return [
            MappedEvidence(
                evidence=piece_of_evidence,
                coordinate=dict(
                    zip(
                        dimension_names,
                        (getattr(prediction, field) for field in subtopic_fields),
                    )
                ),
            )
            for piece_of_evidence, prediction in zip(evidence, results)
        ]
