// The API has no plan of its own: the client posts a step name and the server
// runs it. This mirrors demo/app.js PLAN, which is the canonical order.

export const PLAN = [
  { type: 'enhance_sparse_query', asks: true, mode: 'sparse', title: 'Draft search queries' },
  { type: 'retrieve_sparse_evidence', mode: 'sparse', title: 'Search by query' },
  { type: 'generate_concept_filters', asks: true, mode: 'taxonomy', title: 'Choose taxonomy concepts' },
  { type: 'retrieve_concept_evidence', mode: 'taxonomy', title: 'Search by concept' },
  { type: 'generate_screening_criteria', asks: true, title: 'Set screening criteria' },
  { type: 'screen_evidence', title: 'Screen the evidence' },
  { type: 'generate_map_dimensions', asks: true, map: 'suggested', title: 'Choose map dimensions' },
  { type: 'generate_map_subtopics', asks: true, map: 'suggested', title: 'Fill in subtopics' },
  { type: 'generate_map', map: 'suggested', title: 'Place evidence on the map' },
  { type: 'generate_taxonomy_map', map: 'taxonomy', title: 'Map along taxonomy schemes' },
]

export const STEP = Object.fromEntries(PLAN.map((step) => [step.type, step]))

/** The steps a session actually runs, given its retrieval and mapping modes. */
export function planFor({ mode = 'both', mapMode = 'suggested' } = {}) {
  return PLAN.filter(
    (step) =>
      (!step.mode || mode === 'both' || step.mode === mode) && (!step.map || step.map === mapMode),
  )
}

/** Title for a step type, falling back to the raw type so nothing renders blank. */
export const titleOf = (type) => STEP[type]?.title ?? type
