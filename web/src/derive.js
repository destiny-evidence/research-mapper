// Pure functions over API payloads. No fetching, no components.

import { planFor } from './plan.js'

/** Newest operation per step type. The list arrives oldest first. */
export function byType(operations) {
  const newest = {}
  for (const operation of operations) {
    if (operation?.type) newest[operation.type] = operation
  }
  return newest
}

const STATE = {
  pending: 'running',
  running: 'running',
  awaiting_input: 'ask',
  complete: 'done',
  failed: 'failed',
}

/** The UI state of a step, given its operation (or none). */
export const stateOf = (operation) => (operation ? (STATE[operation.status] ?? 'todo') : 'todo')

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

// One formatter per step type, against the result dicts the steps actually
// return. Anything without an entry falls through to `genericResult`, so a new
// or changed step degrades to something readable rather than blank.
const RESULT = {
  enhance_sparse_query: (r) => `kept ${r.selected} of ${r.suggested}`,
  generate_screening_criteria: (r) => `kept ${r.selected} of ${r.suggested}`,
  retrieve_sparse_evidence: (r) =>
    join([plural(r.references, 'reference'), r.failed ? `${r.failed} queries failed` : null]),
  retrieve_concept_evidence: (r) => plural(r.references, 'reference'),
  generate_concept_filters: (r) =>
    join([plural(r.filter_groups, 'group'), r.questions ? plural(r.questions, 'question') : null]),
  screen_evidence: (r) =>
    join([
      `${r.included} included`,
      `${r.screened - r.included - (r.failed ?? 0)} excluded`,
      r.failed ? `${r.failed} failed` : null,
    ]),
  generate_map_dimensions: (r) => plural(r.dimensions, 'dimension'),
  generate_map_subtopics: (r) =>
    join([plural(r.dimensions, 'dimension'), plural(r.subtopics, 'subtopic')]),
  generate_map: (r) => join([`${r.mapped} placed`, r.failed ? `${r.failed} failed` : null]),
  generate_taxonomy_map: (r) =>
    join([`${r.mapped} placed`, r.dropped ? `${r.dropped} dropped` : null]),
}

const join = (parts) => parts.filter(Boolean).join(' · ')

const genericResult = (result) =>
  Object.entries(result)
    .filter(([key]) => key !== 'version')
    .map(([key, value]) => `${key.replace(/_/g, ' ')} ${value}`)
    .join(' · ')

/** Progress of a running operation, e.g. "254 of 530". */
export function progressText(progress) {
  if (!progress || !progress.total) return progress?.note || ''
  return join([`${progress.done} of ${progress.total}`, progress.failed ? `${progress.failed} failed` : null])
}

/** The one line a collapsed step shows. */
export function summarise(operation) {
  if (!operation) return ''
  if (operation.status === 'failed') {
    const attempts = operation.attempt > 1 ? ` after ${operation.attempt} attempts` : ''
    return `failed${attempts}`
  }
  if (operation.status === 'awaiting_input') return ''
  if (operation.status === 'complete' && operation.result) {
    const format = RESULT[operation.type]
    try {
      return format ? format(operation.result) : genericResult(operation.result)
    } catch {
      return genericResult(operation.result)
    }
  }
  return progressText(operation.progress)
}

/**
 * The step list a session view renders: one row per planned step, in order,
 * carrying its operation, state, summary and any open decisions.
 */
export function steps({ session, operations = [], decisions = [] }) {
  const newest = byType(operations)
  // Loose: an answer is absent whether it comes back null or not at all.
  const open = decisions.filter((decision) => decision.answer == null)
  return planFor(session?.params).map((step) => {
    const operation = newest[step.type]
    const questions = operation ? open.filter((d) => d.operation_id === operation.id) : []
    return {
      ...step,
      operation,
      state: stateOf(operation),
      summary: summarise(operation),
      questions,
    }
  })
}

/** The step a session is currently sitting on, if any. */
export const activeStep = (rows) =>
  rows.find((row) => row.state === 'ask') ??
  rows.find((row) => row.state === 'failed') ??
  rows.find((row) => row.state === 'running')

/**
 * What changed between a suggested artifact and the chosen one.
 * `key` maps an item to a comparable string.
 */
export function diffChoice(suggested = [], chosen = [], key = JSON.stringify) {
  const suggestedKeys = suggested.map(key)
  const chosenKeys = chosen.map(key)
  return {
    kept: chosen.filter((item) => suggestedKeys.includes(key(item))),
    added: chosen.filter((item) => !suggestedKeys.includes(key(item))),
    removed: suggested.filter((item) => !chosenKeys.includes(key(item))),
  }
}

/**
 * A map payload as a grid: rows from the first dimension, columns from the
 * second, the third offered as a facet. A reference may carry several subtopics
 * within one dimension, so it can legitimately land in more than one cell.
 */
export function buildGrid(map, facet = null) {
  if (!map?.dimensions?.length) return null
  const [rowDim, colDim, facetDim] = map.dimensions
  const rows = rowDim.subtopics.map((s) => s.name)
  const cols = colDim.subtopics.map((s) => s.name)

  const within = (coordinate, dimension, name) => (coordinate?.[dimension.name] ?? []).includes(name)
  const evidence = (map.mapped_evidence ?? []).filter(
    (item) => !facet || within(item.coordinate, facetDim, facet),
  )

  const cells = rows.map((row) =>
    cols.map(
      (col) =>
        evidence.filter(
          (item) => within(item.coordinate, rowDim, row) && within(item.coordinate, colDim, col),
        ).length,
    ),
  )

  return {
    rowDim,
    colDim,
    facetDim,
    rows,
    cols,
    cells,
    placed: evidence.length,
    facets: facetDim.subtopics.map((subtopic) => ({
      name: subtopic.name,
      count: (map.mapped_evidence ?? []).filter((item) =>
        within(item.coordinate, facetDim, subtopic.name),
      ).length,
    })),
  }
}
