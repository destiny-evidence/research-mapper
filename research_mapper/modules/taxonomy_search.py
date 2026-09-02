import difflib
import logging

import dspy
from rdflib import Graph

from research_mapper.models.common import UserQuery
from research_mapper.models.react import Step
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.modules.react import ResumableReAct
from research_mapper.signatures.taxonomy_search import (
    GatherEvidenceFromConceptFilters,
    TaxonomyConceptFiltersFromUserQuery,
)
from research_mapper.taxonomy import RepoCommunity
from research_mapper.tools.taxonomy_search import (
    RetrieveEvidenceByConceptsTool,
    TaxonomyBrowsingTools,
    ask_for_clarification,
    mark_unsatisfiable,
    raise_attempted_prompt_attack,
)
from research_mapper.ui.tui import TerminalUI

logger = logging.getLogger(__name__)

NOT_SURE_OPTION = "I'm not sure"
NONE_OF_THESE_OPTION = "None of these"
SENTINEL_OPTIONS = (NONE_OF_THESE_OPTION, NOT_SURE_OPTION)

CLARIFY_TOOL = ask_for_clarification.__name__
GIVE_UP_TOOLS = frozenset(
    {mark_unsatisfiable.__name__, raise_attempted_prompt_attack.__name__}
)


class UnknownConceptRefError(ValueError):
    """Raised when the agent's final output cites a local_ref that isn't part
    of the indexed vocabulary it was exploring — this is what used to crash
    downstream (e.g. a KeyError in a TUI display lambda) instead of surfacing
    clearly at the point the bad ref was actually produced."""


class TaxonomyConceptFilterGenerator(dspy.Module):
    """
    Generates a set of taxonomy concepts to filter references with, driving a
    ResumableReAct agent step by step so every reasoning step can be shown
    live, and so ask_for_clarification/mark_unsatisfiable can be answered or
    inspected by this caller before their (otherwise trivial) tool bodies
    ever run — neither tool touches the TUI or holds any state itself. The
    agent explores the taxonomy on demand via TaxonomyBrowsingTools rather
    than having it all handed to it upfront, so it's built fresh per call —
    its tools are bound to that call's community-specific indexed vocab/graph.
    """

    def __init__(self, ui: TerminalUI | None = None) -> None:
        self.ui = ui

    def forward(
        self, user_query: UserQuery, indexed: IndexedVocab, graph: Graph
    ) -> dspy.Prediction:
        """
        Runs an agent to interactively generate a set of concepts to filter references on.
        A thin, blocking caller of start()/resume(). It just keeps approving every
        step, answering clarifications via self.ui, until the run finishes. The
        workflow-engine's GenerateConceptFilters step is the other caller of
        start()/resume(): same underlying interface, different (non-blocking,
        persist-and-suspend) answer to "what do we do at a clarification".
        :param user_query: the original user query
        :param indexed: the community's indexed vocabulary, to explore via tool calls
        :param graph: the community's rdflib Graph, for broader/narrower lookups
        :return: a Prediction wrapping a collection of ConceptFilterGroup instances, plus
            unsatisfiable_reason (None unless the agent flagged the query as unsatisfiable)
        """
        unsatisfiable_reason: str | None = None
        result = self.start(user_query=user_query, indexed=indexed, graph=graph)
        while isinstance(result, Step):
            if self.ui is not None:
                self.ui.print_reasoning(f"Step {result.idx}", result.thought)
            outcome = self.classify_step(result)
            if isinstance(outcome, str):
                unsatisfiable_reason = outcome
            elif isinstance(outcome, ClarificationOptions) and self.ui is not None:
                answer = self._prompt_clarification(outcome)
                result = result.with_observation(answer)
            result = self.resume(
                result, user_query=user_query, indexed=indexed, graph=graph
            )
        return dspy.Prediction(
            filter_groups=result.filter_groups,
            reasoning=result.reasoning,
            unsatisfiable_reason=unsatisfiable_reason,
        )

    def start(
        self,
        user_query: UserQuery,
        indexed: IndexedVocab,
        graph: Graph,
        *,
        can_ask: bool | None = None,
    ) -> Step | dspy.Prediction:
        """
        Begins a run, the resumable counterpart to forward(): returns a Step
        for the caller to drive further (deciding for itself how to answer a
        clarification, and how/whether to persist the Step across a suspend
        boundary), or the final, validated Prediction once the run finishes.
        """
        self.agent = self.build_agent(indexed, graph, can_ask=can_ask)
        return self._validated(
            self.agent.start(
                user_query=user_query, available_concepts=self.concept_listing(indexed)
            ),
            indexed,
        )

    def resume(
        self,
        step: Step | None,
        user_query: UserQuery,
        indexed: IndexedVocab,
        graph: Graph,
        *,
        can_ask: bool | None = None,
    ) -> Step | dspy.Prediction:
        """
        Advances a run by one iteration, the resumable counterpart to what
        used to be forward()'s internal loop body. Rebuilds the agent fresh
        on every call: ResumableReAct carries no per-run state on self, only
        the compiled program (tools/predictors), the run's actual progress
        lives entirely in `step.trajectory`. So this is cheap and behaves
        identically to reusing one instance across a run.
        """
        self.agent = self.build_agent(indexed, graph, can_ask=can_ask)
        return self._validated(
            self.agent.resume(
                step,
                user_query=user_query,
                available_concepts=self.concept_listing(indexed),
            ),
            indexed,
        )

    def _validated(
        self, result: Step | dspy.Prediction, indexed: IndexedVocab
    ) -> Step | dspy.Prediction:
        if not isinstance(result, Step):
            self.validate_filter_groups(result.filter_groups, indexed)
        return result

    def classify_step(self, step: Step) -> str | ClarificationOptions | None:
        """
        The one place that knows which of this module's own tools are
        meaningful pause points and what they mean, so every caller (the
        TUI's forward(), the workflow engine's GenerateConceptFilters step)
        dispatches on the same pre-classified outcome instead of each
        re-deriving "what does this tool_name mean" from a Step's raw
        tool_name/tool_args itself.
        :return: the give-up reason (str) if the agent gave up, the parsed
            clarification request if it's asking the user something, or None
            if this step isn't a pause point at all, just call resume()
        """
        if step.tool_name in GIVE_UP_TOOLS:
            return step.tool_args["reason"]
        if step.tool_name == CLARIFY_TOOL:
            return ClarificationOptions(**step.tool_args["request"])
        return None

    def validate_filter_groups(
        self, filter_groups: list[ConceptFilterGroup], indexed: IndexedVocab
    ) -> None:
        """
        Guards against the agent citing a local_ref that was never a real
        concept — e.g. mis-parsed out of a compound string — before it can
        crash something downstream. Suggestions are matched against concept
        labels, not refs: refs are short alphanumeric codes fuzzy matching
        finds too noisy to be useful, but labels reliably surface the
        agent's likely intended concept.
        """
        if not filter_groups:
            return
        known_refs = {concept.local_ref for concept in indexed.concepts}
        for group in filter_groups:
            for ref in group.concept_local_refs:
                if ref in known_refs:
                    continue
                raise UnknownConceptRefError(
                    self._unknown_ref_message(ref, group.scheme, indexed)
                )

    def _unknown_ref_message(self, ref: str, scheme: str, indexed: IndexedVocab) -> str:
        msg = f"Unknown concept local_ref {ref!r} in scheme {scheme!r}."
        # Labels repeat across schemes (e.g. "Caregivers" appears in 3 HPV
        # schemes), so suggestions are scoped to the cited scheme first,
        # only falling back to the whole vocabulary if that scheme itself
        # turns out to have nothing close, e.g. because it too was mis-cited.
        suggestions = self._suggest_concepts(
            ref, [concept for concept in indexed.concepts if concept.scheme == scheme]
        )
        if not suggestions:
            suggestions = self._suggest_concepts(ref, indexed.concepts)
        if suggestions:
            msg += f" Did you mean one of: {', '.join(suggestions)}?"
        return msg

    def _suggest_concepts(
        self, ref: str, concepts: list[Concept], n: int = 3, cutoff: float = 0.4
    ) -> list[str]:
        """Fuzzy-matches `ref` against `concepts`' labels, deduplicated by
        label within this candidate set so a repeated label always
        resolves to a concept that's actually a member of it (the scheme
        being searched, or the whole vocabulary on fallback), never a
        leftover from a different call's candidate set."""
        by_label = {concept.label: concept for concept in concepts}
        matches = difflib.get_close_matches(ref, list(by_label), n=n, cutoff=cutoff)
        return [
            f"{by_label[label].local_ref} ({by_label[label].scheme}: {label})"
            for label in matches
        ]

    def concept_listing(self, indexed: IndexedVocab) -> str:
        """A flat 'local_ref\tscheme: label' line per concept — cheap enough (a
        few thousand tokens even for HPV's 575 concepts) to hand the agent
        upfront so it can cite a concept straight from here instead of
        guessing wording, or paying a lookup_concepts call per ref."""
        return "\n".join(
            f"{concept.local_ref}\t{concept.scheme}: {concept.label}"
            for concept in sorted(
                indexed.concepts, key=lambda concept: (concept.scheme, concept.label)
            )
        )

    def build_agent(
        self, indexed: IndexedVocab, graph: Graph, *, can_ask: bool | None = None
    ) -> ResumableReAct:
        """Defaults to whether there is a UI to answer through."""
        if can_ask is None:
            can_ask = self.ui is not None
        browsing = TaxonomyBrowsingTools(graph, indexed)
        tools = [
            browsing.list_schemes,
            browsing.list_concepts_in_scheme,
            browsing.lookup_concepts,
            browsing.get_concept_detail,
            browsing.get_broader,
            browsing.get_narrower,
            mark_unsatisfiable,
            raise_attempted_prompt_attack,
        ]
        if can_ask:
            tools.append(ask_for_clarification)
        return ResumableReAct(
            signature=TaxonomyConceptFiltersFromUserQuery,
            tools=tools,
            max_iters=50,
        )

    def _prompt_clarification(self, request: ClarificationOptions) -> list[str]:
        """
        Answers one proposed `ask_for_clarification` call by prompting the TUI. Only
        ever reached when `self.ui` is set — that's the only case `ask_for_clarification`
        is registered as a tool at all, so the agent can only propose it then.
        """
        options = [*request.options, *SENTINEL_OPTIONS]
        self.ui.print_info(request.question)
        while True:
            selected = self.ui.select_from_list(options, default=[len(options)])
            if len(selected) > 1 and NONE_OF_THESE_OPTION in selected:
                self.ui.print_info(
                    '[red]"None of these" can\'t be combined '
                    "with other options — try again.[/red]"
                )
                continue
            return selected


class ConceptEvidenceRetriever(dspy.Module):
    """
    Dispatches a DSPy subagent to retrieve Evidence from the DESTINY repository for a
    fixed set of concept filters, deciding pagination/stopping itself.
    """

    def forward(
        self,
        user_query: UserQuery,
        community: RepoCommunity,
        filter_groups: list[ConceptFilterGroup],
        concepts: list[str | list[str]],
    ) -> dspy.Prediction:
        """
        Retrieves Evidence for a fixed set of concept filters.
        :param user_query: the original user query, for context
        :param community: the repository community to retrieve evidence from
        :param filter_groups: the concept filters, for the subagent's context
        :param concepts: the concept filters resolved to IRIs, to fix the retrieval tool with
        :return: a Prediction wrapping the retrieved evidence, alongside the subagent's
            search_summary, stopping_reason, and reasoning
        """
        tool = RetrieveEvidenceByConceptsTool(community, concepts)
        subagent = dspy.ReAct(
            signature=GatherEvidenceFromConceptFilters,
            tools=[tool.retrieve_evidence],
            max_iters=5,
        )
        prediction = subagent(original_query=user_query, filter_groups=filter_groups)

        logger.info("Found %d new items for concept filters", len(tool.retrieved))
        logger.debug("Search summary: %s", prediction.search_summary)
        logger.info('Agent stopped searching because: "%s"', prediction.stopping_reason)
        return dspy.Prediction(
            evidence=list(tool.retrieved.values()),
            search_summary=prediction.search_summary,
            stopping_reason=prediction.stopping_reason,
            reasoning=prediction.reasoning,
        )
