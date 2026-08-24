"""Run the API or the worker with the LLM and DESTINY replaced by canned data.

Disposable, like the rest of demo/. It reaches into workflow internals so the UI can be
demoed with no credentials, no network and no spend. Expect it to rot; delete it freely.

    uv run python demo/offline.py api
    uv run python demo/offline.py worker
"""

import argparse
import asyncio
import hashlib
import os
import random
import time
import uuid

import dspy

from research_mapper.models.common import Evidence
from research_mapper.models.taxonomy_search import (
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)

DELAY = float(os.environ.get("DEMO_DELAY", "0.3"))

SETTINGS = ["School-based", "Primary care", "Pharmacy-led", "Community outreach"]
POPULATIONS = [
    "Adolescent girls",
    "Adolescent boys",
    "Young adults",
    "Parents and carers",
]
OUTCOMES = ["Vaccine uptake", "Series completion", "Consent rates", "Vaccine hesitancy"]
DESIGNS = [
    "a cluster randomised trial",
    "a retrospective cohort study",
    "a mixed-methods evaluation",
    "a qualitative interview study",
    "a national registry analysis",
]
JOURNALS = [
    "Vaccine",
    "BMJ Open",
    "Pediatrics",
    "Lancet Public Health",
    "Health Promotion International",
]
SURNAMES = [
    "Okafor",
    "Lindqvist",
    "Baptista",
    "Nakamura",
    "Duarte",
    "Haddad",
    "Whitfield",
    "Ivanova",
    "Mensah",
    "Rossi",
]

# Two combinations are deliberately absent, so the map has real gaps to point at.
GAPS = {("Pharmacy-led", "Consent rates"), ("Community outreach", "Series completion")}

DIMENSIONS = [
    {"name": "Setting", "description": "Where the vaccination was delivered"},
    {"name": "Population", "description": "Who the study was about"},
    {"name": "Outcome", "description": "What the study measured"},
]
SUBTOPICS = {"Setting": SETTINGS, "Population": POPULATIONS, "Outcome": OUTCOMES}

CONCEPTS = [
    Concept(local_ref=f"C{i}", scheme="Delivery setting", label=name)
    for i, name in enumerate(SETTINGS)
]
INDEX = IndexedVocab(
    concepts=CONCEPTS,
    local_ref_to_iri={
        c.local_ref: f"https://vocab.example/setting/{i}"
        for i, c in enumerate(CONCEPTS)
    },
)


def _uuid(seed: str) -> uuid.UUID:
    """A stable v4-shaped id, because DESTINY ids must be v4 or v7."""
    digest = bytearray(hashlib.md5(seed.encode()).digest())
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(digest))


def _library() -> tuple[
    dict[uuid.UUID, Evidence], dict[uuid.UUID, tuple[str, str, str]]
]:
    """A fixed shelf of papers, each built from the coordinate it will be mapped to."""
    rng = random.Random(11)
    combinations = [
        (setting, population, outcome)
        for setting in SETTINGS
        for population in POPULATIONS
        for outcome in OUTCOMES
        if (setting, outcome) not in GAPS
    ]
    papers, coordinates = {}, {}
    for index, (setting, population, outcome) in enumerate(
        rng.sample(combinations, 34)
    ):
        destiny_id = _uuid(f"paper-{index}")
        title = (
            f"{setting} HPV vaccination and {outcome.lower()} among {population.lower()}: "
            f"{rng.choice(DESIGNS)}"
        )
        papers[destiny_id] = Evidence(
            destiny_id=destiny_id,
            title=title,
            abstract=(
                f"We examined {outcome.lower()} following {setting.lower()} HPV vaccination "
                f"delivered to {population.lower()} across {rng.randint(3, 40)} sites."
            ),
            authors=[
                f"{rng.choice(SURNAMES)}, {chr(rng.randint(65, 90))}."
                for _ in range(rng.randint(2, 4))
            ],
            year=rng.randint(2014, 2025),
            publisher=rng.choice(JOURNALS),
            landing_page_urls=[f"https://example.org/paper/{index}"],
        )
        coordinates[destiny_id] = (setting, population, outcome)
    return papers, coordinates


PAPERS, COORDINATES = _library()
SHELF = list(PAPERS.values())


def _sleep() -> None:
    if DELAY:
        time.sleep(DELAY)


def _queries(**_):
    _sleep()
    return dspy.Prediction(
        search_queries=[
            {"query": 'title:("HPV vaccination") AND abstract:(uptake OR coverage)'},
            {"query": 'abstract:("school-based" AND (immunisation OR immunization))'},
            {"query": "title:(adolescent AND vaccine AND (consent OR refusal))"},
            {"query": 'abstract:("vaccine hesitancy") AND title:(HPV)'},
            {
                "query": 'title:("human papillomavirus") AND abstract:("series completion")'
            },
        ],
        reasoning="Four angles: the intervention, the setting, the decision point, and the barrier.",
    )


def _sparse_search(search_query, **_):
    _sleep()
    _sleep()
    offset = sum(ord(c) for c in search_query.query) % 5
    return dspy.Prediction(
        evidence=SHELF[offset::5],
        search_summary=f"{len(SHELF[offset::5])} references matched",
        stopping_reason="no further pages",
    )


def _concept_search(**_):
    _sleep()
    return dspy.Prediction(
        evidence=SHELF[-9:],
        search_summary="9 references carried the selected concepts",
        stopping_reason="no further pages",
    )


def _criteria(**_):
    _sleep()
    return dspy.Prediction(
        screening_criteria=[
            {
                "criterion_type": "inclusion",
                "description": "Reports an HPV vaccination programme",
            },
            {
                "criterion_type": "inclusion",
                "description": "Reports a quantitative uptake or completion measure",
            },
            {
                "criterion_type": "inclusion",
                "description": "Published from 2014 onwards",
            },
            {
                "criterion_type": "exclusion",
                "description": "Modelling study with no empirical population",
            },
            {
                "criterion_type": "exclusion",
                "description": "Editorial, letter or conference abstract",
            },
        ],
        reasoning="Scoped to empirical programme evaluations rather than commentary.",
    )


def _screen(evidence, **_):
    _sleep()
    include = (
        int(hashlib.md5(str(evidence.destiny_id).encode()).hexdigest(), 16) % 4 != 0
    )
    return dspy.Prediction(
        include=include,
        reasoning="Meets the inclusion criteria."
        if include
        else "No empirical uptake measure reported.",
    )


def _dimensions(**_):
    _sleep()
    return dspy.Prediction(
        dimension1=DIMENSIONS[0],
        dimension2=DIMENSIONS[1],
        dimension3=DIMENSIONS[2],
        reasoning="Setting, population and outcome are the axes this literature actually varies on.",
    )


def _subtopics(dimension, **_):
    _sleep()
    return dspy.Prediction(
        subtopics=[
            {"name": name, "description": f"{name} studies"}
            for name in SUBTOPICS[dimension.name]
        ],
        reasoning=f"The recurring buckets within {dimension.name}.",
    )


def _place(evidence, **_):
    _sleep()
    setting, population, outcome = COORDINATES[evidence.destiny_id]
    return dspy.Prediction(
        dimension1_subtopic=setting,
        dimension2_subtopic=population,
        dimension3_subtopic=outcome,
        reasoning="Placed from the abstract's stated setting, population and outcome.",
    )


def _get_evidence(reference_ids):
    return (
        [{i: PAPERS[i] for i in reference_ids if i in PAPERS}] if reference_ids else []
    )


class _Agent:
    """A ResumableReAct stand-in that asks the user one question, then answers."""

    def start(self, **_):
        from research_mapper.models.react import Step

        _sleep()
        return Step(
            trajectory={
                "thought_0": "The question does not say where vaccination happens."
            },
            idx=0,
            thought="The question does not say where vaccination happens.",
            tool_name="ask_for_clarification",
            tool_args={
                "request": {
                    "question": "Which delivery settings are in scope?",
                    "options": SETTINGS,
                }
            },
        )

    def resume(self, step, **_):
        _sleep()
        chosen = step.trajectory.get("observation_0") or SETTINGS
        refs = [c.local_ref for c in CONCEPTS if c.label in chosen] or ["C0"]
        return dspy.Prediction(
            filter_groups=[
                ConceptFilterGroup(
                    scheme="Delivery setting",
                    concept_local_refs=refs,
                    reason="The settings you confirmed are in scope.",
                )
            ],
            reasoning="Narrowed the taxonomy to the settings you picked.",
        )


def apply() -> None:
    """Rebind every outbound call in the workflow to the canned versions above."""
    from research_mapper.workflows.evidence_map import hydrate, routes
    from research_mapper.workflows.evidence_map.steps import (
        concept_filters,
        mapping,
        retrieve,
        screening,
        sparse_query,
    )

    sparse_query.SparseQueryGenerator = lambda: _queries
    retrieve.EvidenceRetriever = lambda: _sparse_search
    retrieve.ConceptEvidenceRetriever = lambda: _concept_search
    screening.CriteriaGenerator = lambda: _criteria
    screening.EvidenceScreener = lambda: _screen
    mapping.DimensionGenerator = lambda: _dimensions
    mapping.SubtopicGenerator = lambda: _subtopics
    mapping.EvidenceMapper = lambda: _place
    concept_filters.get_taxonomy = lambda community: {}
    concept_filters.build_concept_index = lambda vocab: INDEX
    concept_filters.build_concept_filter_agent = _Agent
    for module in (hydrate, screening, mapping, routes):
        module.get_evidence = _get_evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["api", "worker"])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    arguments = parser.parse_args()

    from research_mapper import commands
    from research_mapper.config import init_database, load_environment

    load_environment()
    apply()
    init_database()
    if arguments.role == "api":
        import uvicorn

        uvicorn.run(
            "research_mapper.api.app:app", host=arguments.host, port=arguments.port
        )
    else:
        asyncio.run(commands._worker())


if __name__ == "__main__":
    main()
