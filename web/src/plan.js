// Ordered steps to run
export const PLAN = [
  {
    type: "enhance_sparse_query",
    mode: "sparse",
    regenerate: true,
    title: "Draft search queries",
  },
  {
    type: "retrieve_sparse_evidence",
    mode: "sparse",
    title: "Search by query",
  },
  {
    type: "generate_concept_filters",
    mode: "taxonomy",
    title: "Choose taxonomy concepts",
  },
  {
    type: "retrieve_concept_evidence",
    mode: "taxonomy",
    title: "Search by concept",
  },
  {
    type: "generate_screening_criteria",
    regenerate: true,
    title: "Set screening criteria",
  },
  { type: "screen_evidence", title: "Screen the evidence" },
  {
    type: "generate_map_dimensions",
    map: "suggested",
    regenerate: true,
    title: "Choose map dimensions",
  },
  {
    type: "generate_map_subtopics",
    map: "suggested",
    regenerate: true,
    title: "Fill in subtopics",
  },
  {
    type: "generate_map",
    map: "suggested",
    title: "Place evidence on the map",
  },
  {
    type: "generate_taxonomy_map",
    map: "taxonomy",
    title: "Map along taxonomy schemes",
  },
];

export const STEP = Object.fromEntries(PLAN.map((step) => [step.type, step]));

export const MAP_TAILS = {
  suggested: {
    head: "generate_map_dimensions",
    label: "Let it suggest dimensions from your question",
    detail:
      "The agent proposes three novel axes. You can edit or update them, then it places each reference on the map.",
  },
  taxonomy: {
    head: "generate_taxonomy_map",
    label: "Use the taxonomy's own schemes",
    detail:
      "The agent selects axes from the taxonomy. References are placed on the map according to their existing coded values.",
  },
};

export function planFor({ mode = "both" } = {}, mapTail = null) {
  return PLAN.filter(
    (step) =>
      (!step.mode || mode === "both" || step.mode === mode) &&
      (!step.map || step.map === mapTail),
  );
}

export function tailOf(operations = []) {
  const types = new Set(operations.map((operation) => operation?.type));
  return (
    Object.keys(MAP_TAILS).find((tail) =>
      PLAN.some((step) => step.map === tail && types.has(step.type)),
    ) ?? null
  );
}

export const titleOf = (type) => STEP[type]?.title ?? type;
