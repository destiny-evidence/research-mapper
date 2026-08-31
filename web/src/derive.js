// Pure functions over API payloads. No fetching, no components.

import { MAP_TAILS, planFor, tailOf } from './plan.js'

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
  enhance_sparse_query: (r) => `selected ${r.selected} of ${r.suggested}`,
  generate_screening_criteria: (r) => `selected ${r.selected} of ${r.suggested}`,
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

/**
 * Progress of a running operation, e.g. "254 of 530". Plenty of steps are a
 * single model call and have nothing to count, so they say what they are doing
 * instead of reporting "0".
 */
export function progressText(progress) {
  if (!progress?.total) return progress?.note || 'Thinking'
  return join([`${progress.done} of ${progress.total}`, progress.failed ? `${progress.failed} failed` : null])
}

/** Whether an operation has counts worth showing, or is just working. */
export const hasCounts = (progress) => Boolean(progress?.total)

/** The one line a collapsed step shows. */
export function summarise(operation) {
  if (!operation) return ''
  if (operation.status === 'failed') return 'Failed'
  if (operation.status === 'awaiting_input') return ''
  if (operation.status === 'pending') return 'Queued'
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
 * carrying its operation, state, summary and whatever it is waiting to be asked.
 */
export const MAP_BRANCH = 'choose-how-to-map'

export function steps({ session, operations = [] }) {
  const newest = byType(operations)
  const tail = tailOf(operations)
  const rows = planFor(session?.params, tail).map((step) => {
    const operation = newest[step.type]
    // Plural: ctx.ask_all can park an operation on several questions at once.
    const questions = operation?.pending_questions ?? []
    return {
      ...step,
      operation,
      state: stateOf(operation),
      summary: summarise(operation),
      questions,
    }
  })

  // Until a mapping tail is started the plan genuinely stops here, so the thread
  // shows the choice rather than pretending to know what comes next. It only
  // asks once everything before it is done — before that it is just the horizon.
  if (tail) return rows
  const reachable = rows.every((row) => row.state === 'done')
  return [
    ...rows,
    {
      type: MAP_BRANCH,
      title: 'Build the map',
      state: reachable ? 'ask' : 'todo',
      summary: '',
      branch: reachable ? MAP_TAILS : null,
      questions: [],
    },
  ]
}

/**
 * The step the client should queue next, or null. The API runs a step when it
 * is asked to and never advances on its own, so this is what keeps a session
 * moving. A step that already has an operation is left alone — including a
 * failed one, because retrying is the user's call.
 */
export function nextToStart(rows) {
  const next = rows.find((row) => row.state !== 'done')
  // A branch is the user's to resolve; queueing anything past it would be
  // guessing which map they want.
  if (!next || next.branch) return null
  return next.operation ? null : next.type
}

/**
 * Whether the map is built. Either mapping step produces it — generate_map from
 * agreed dimensions, generate_taxonomy_map from the taxonomy's own schemes —
 * and both write the same artifact and the same coordinates, so the map view
 * does not care which ran.
 */
export const mapIsReady = (rows) =>
  rows.some(
    (row) => ['generate_map', 'generate_taxonomy_map'].includes(row.type) && row.state === 'done',
  )

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
 * A map payload as a grid. Any two dimensions can be the axes; the third
 * becomes the facet. A reference may carry several subtopics within one
 * dimension, so it can legitimately land in more than one cell.
 */
export function buildGrid(map, { row = 0, col = 1, facet = null } = {}) {
  if (map?.dimensions?.length !== 3 || row === col) return null
  const facetIndex = [0, 1, 2].find((index) => index !== row && index !== col)
  const rowDim = map.dimensions[row]
  const colDim = map.dimensions[col]
  const facetDim = map.dimensions[facetIndex]

  const within = (coordinate, dimension, name) => (coordinate?.[dimension.name] ?? []).includes(name)
  const all = map.mapped_evidence ?? []
  const evidence = all.filter((item) => !facet || within(item.coordinate, facetDim, facet))

  // A dimension can carry the same subtopic name twice — the taxonomy tail turns
  // every concept in a scheme into a subtopic, and two concepts can share a label.
  // Left in, the name would draw two identical rows counting the same evidence.
  const names = (dimension) => [...new Set(dimension.subtopics.map((s) => s.name))]
  const rows = names(rowDim)
  const cols = names(colDim)
  const cells = rows.map((name) =>
    cols.map(
      (other) =>
        evidence.filter(
          (item) => within(item.coordinate, rowDim, name) && within(item.coordinate, colDim, other),
        ).length,
    ),
  )

  return {
    rowDim,
    colDim,
    facetDim,
    rowIndex: row,
    colIndex: col,
    facetIndex,
    rows,
    cols,
    cells,
    maxCount: Math.max(0, ...cells.flat()),
    placed: evidence.length,
    total: all.length,
    facets: facetDim.subtopics.map((subtopic) => ({
      name: subtopic.name,
      count: all.filter((item) => within(item.coordinate, facetDim, subtopic.name)).length,
    })),
  }
}
