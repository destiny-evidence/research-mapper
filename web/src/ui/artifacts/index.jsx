import { Queries } from './Queries.jsx'
import { Criteria } from './Criteria.jsx'
import { ConceptFilters } from './ConceptFilters.jsx'
import { Dimensions } from './Dimensions.jsx'

/**
 * One renderer per artifact type, plus the suggested twin it is diffed against.
 * A new artifact type is one file and one entry here; an unknown one falls back
 * to raw JSON rather than breaking the page.
 */
export const RENDERERS = {
  search_queries: { render: Queries, suggests: 'suggested_search_queries' },
  screening_criteria: { render: Criteria, suggests: 'suggested_screening_criteria' },
  concept_filters: { render: ConceptFilters, suggests: 'suggested_concept_filters' },
  map_dimensions: { render: Dimensions, suggests: 'suggested_map_dimensions' },
  dimensions: { render: Dimensions, suggests: 'suggested_dimension_subtopics' },
}

/** Artifact types worth showing in a step panel, in the order they are produced. */
export const SHOWN = Object.keys(RENDERERS)

export function Artifact({ type, payload, suggested }) {
  const entry = RENDERERS[type]
  if (!entry) return <Json payload={payload} />
  const Render = entry.render
  try {
    return <Render payload={payload} suggested={suggested} />
  } catch {
    // A payload that has moved on from what the renderer expects should show
    // the data, not a blank panel.
    return <Json payload={payload} />
  }
}

const Json = ({ payload }) => (
  <pre class="mono" style="font-size: 11px; color: var(--text); background: var(--tint); border: 1px solid var(--line-2); padding: 10px; overflow-x: auto; max-width: 640px;">
    {JSON.stringify(payload, null, 2)}
  </pre>
)

/**
 * The suggestion an asking step is asking about. Written before the step parks,
 * so its reasoning is available while the question is still open — which is
 * when it is actually useful.
 *
 * generate_concept_filters is absent on purpose: its question comes from the
 * ReAct loop, and the thinking behind it is the pending step's own thought,
 * which the trace already shows.
 */
export const SUGGESTION_FOR_STEP = {
  enhance_sparse_query: 'suggested_search_queries',
  generate_screening_criteria: 'suggested_screening_criteria',
  generate_map_dimensions: 'suggested_map_dimensions',
  generate_map_subtopics: 'suggested_dimension_subtopics',
}

/** Every artifact type the session view fetches. */
export const WANTED = new Set([
  ...Object.keys(RENDERERS),
  ...Object.values(RENDERERS).map((entry) => entry.suggests),
  ...Object.values(SUGGESTION_FOR_STEP),
  'concept_filter_loop',
])

/** The artifact a completed step is worth showing, if any. */
export const ARTIFACT_FOR_STEP = {
  enhance_sparse_query: 'search_queries',
  generate_screening_criteria: 'screening_criteria',
  generate_concept_filters: 'concept_filters',
  generate_map_dimensions: 'map_dimensions',
  generate_map_subtopics: 'dimensions',
  // Picks its own axes from the taxonomy's schemes and writes the same artifact.
  generate_taxonomy_map: 'dimensions',
}
