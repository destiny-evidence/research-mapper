// The API has no plan of its own: the client posts a step name and the server
// runs it. This mirrors demo/app.js PLAN, which is the canonical order.

export const PLAN = [
  { type: 'enhance_sparse_query', mode: 'sparse', title: 'Draft search queries' },
  { type: 'retrieve_sparse_evidence', mode: 'sparse', title: 'Search by query' },
  { type: 'generate_concept_filters', mode: 'taxonomy', title: 'Choose taxonomy concepts' },
  { type: 'retrieve_concept_evidence', mode: 'taxonomy', title: 'Search by concept' },
  { type: 'generate_screening_criteria', title: 'Set screening criteria' },
  { type: 'screen_evidence', title: 'Screen the evidence' },
  { type: 'generate_map_dimensions', map: 'suggested', title: 'Choose map dimensions' },
  { type: 'generate_map_subtopics', map: 'suggested', title: 'Fill in subtopics' },
  { type: 'generate_map', map: 'suggested', title: 'Place evidence on the map' },
  { type: 'generate_taxonomy_map', map: 'taxonomy', title: 'Map along taxonomy schemes' },
]

export const STEP = Object.fromEntries(PLAN.map((step) => [step.type, step]))

/**
 * How the map can be built. The choice is not recorded anywhere: whichever
 * tail has an operation *is* the choice, and that is already persisted.
 */
export const MAP_TAILS = {
  suggested: {
    head: 'generate_map_dimensions',
    label: 'Let it suggest dimensions from your question',
    detail: 'It proposes three axes, you edit them, then it places each reference.',
  },
  taxonomy: {
    head: 'generate_taxonomy_map',
    label: "Use the taxonomy's own schemes",
    detail: 'Axes come from the taxonomy, and placement from the tags each reference already has. No questions.',
  },
}

/**
 * The steps a session runs. Search mode is a session param; the mapping tail is
 * only known once one has been started, so until then the plan stops short.
 */
export function planFor({ mode = 'both' } = {}, mapTail = null) {
  return PLAN.filter(
    (step) =>
      (!step.mode || mode === 'both' || step.mode === mode) && (!step.map || step.map === mapTail),
  )
}

/** Which mapping tail this session took, if it has taken one. */
export function tailOf(operations = []) {
  const types = new Set(operations.map((operation) => operation?.type))
  return (
    Object.keys(MAP_TAILS).find((tail) =>
      PLAN.some((step) => step.map === tail && types.has(step.type)),
    ) ?? null
  )
}

/** Title for a step type, falling back to the raw type so nothing renders blank. */
export const titleOf = (type) => STEP[type]?.title ?? type
