import { describe, expect, it } from 'vitest'
import { MAP_BRANCH } from '../src/derive.js'
import {
  buildGrid,
  byType,
  diffChoice,
  mapIsReady,
  nextToStart,
  stateOf,
  steps,
  summarise,
} from '../src/derive.js'

const operation = (type, extra = {}) => ({
  id: `op-${type}`,
  type,
  status: 'complete',
  attempt: 1,
  progress: {},
  decisions: [],
  ...extra,
})

describe('summarise', () => {
  it('reads the screening result the way the step reports it', () => {
    const result = { screened: 530, included: 94, failed: 3 }
    expect(summarise(operation('screen_evidence', { result }))).toBe(
      '94 included · 433 excluded · 3 failed',
    )
  })

  it('leaves out counts the step did not report', () => {
    const result = { queries: 4, references: 412, failed: 0 }
    expect(summarise(operation('retrieve_sparse_evidence', { result }))).toBe('412 references')
  })

  it('says a step failed and leaves the detail to the panel', () => {
    expect(summarise(operation('generate_concept_filters', { status: 'failed', attempt: 2 }))).toBe(
      'Failed',
    )
  })

  it('falls back to the raw result for a step it has no formatter for', () => {
    const result = { some_count: 7, version: 2 }
    expect(summarise(operation('brand_new_step', { result }))).toBe('some count 7')
  })

  it('shows progress while running', () => {
    const progress = { done: 254, total: 530, failed: 0 }
    expect(summarise(operation('screen_evidence', { status: 'running', progress }))).toBe('254 of 530')
  })

  it('says what it is doing when a step has nothing to count', () => {
    // A single model call reports {done: 0, total: null}, which is not "0".
    const progress = { done: 0, total: null, failed: 0, note: '' }
    expect(summarise(operation('enhance_sparse_query', { status: 'running', progress }))).toBe('Thinking')
  })

  it('prefers the step’s own note over the generic one', () => {
    const progress = { done: 0, total: null, failed: 0, note: 'screening evidence' }
    expect(summarise(operation('screen_evidence', { status: 'running', progress }))).toBe('screening evidence')
  })

  it('distinguishes queued from running', () => {
    expect(summarise(operation('enhance_sparse_query', { status: 'pending', progress: {} }))).toBe('Queued')
  })
})

describe('byType', () => {
  it('keeps the newest operation of a type, since the list is oldest first', () => {
    const older = operation('screen_evidence', { id: 'old' })
    const newer = operation('screen_evidence', { id: 'new' })
    expect(byType([older, newer]).screen_evidence.id).toBe('new')
  })
})

describe('stateOf', () => {
  it('treats a queued operation as running and a missing one as todo', () => {
    expect(stateOf({ status: 'pending' })).toBe('running')
    expect(stateOf({ status: 'awaiting_input' })).toBe('ask')
    expect(stateOf(undefined)).toBe('todo')
  })
})

describe('steps', () => {
  it('carries every open question on an operation, not just the first', () => {
    const asking = operation('generate_map_subtopics', {
      status: 'awaiting_input',
      pending_questions: [
        { id: 1, key: 'first' },
        { id: 2, key: 'second' },
      ],
      decisions: [{ id: 1 }, { id: 2 }, { id: 3, answer: [{ name: 'done' }] }],
    })
    const rows = steps({ session: { params: {} }, operations: [asking] })
    const row = rows.find((entry) => entry.type === 'generate_map_subtopics')
    expect(row.state).toBe('ask')
    expect(row.questions).toHaveLength(2)
  })
})

describe('diffChoice', () => {
  it('separates what was kept, added and removed', () => {
    const suggested = [{ query: 'a' }, { query: 'b' }]
    const chosen = [{ query: 'a' }, { query: 'c' }]
    const diff = diffChoice(suggested, chosen, (item) => item.query)
    expect(diff.kept).toEqual([{ query: 'a' }])
    expect(diff.added).toEqual([{ query: 'c' }])
    expect(diff.removed).toEqual([{ query: 'b' }])
  })
})

const dimension = (name, subtopics) => ({ name, description: '', subtopics: subtopics.map((s) => ({ name: s, description: '' })) })

const MAP = {
  dimensions: [
    dimension('Barrier', ['Cost', 'Hesitancy']),
    dimension('Setting', ['School', 'Facility']),
    dimension('Design', ['Trial', 'Qualitative']),
  ],
  mapped_evidence: [
    { coordinate: { Barrier: ['Cost'], Setting: ['School'], Design: ['Trial'] } },
    { coordinate: { Barrier: ['Cost'], Setting: ['School'], Design: ['Qualitative'] } },
    // Annotated with two subtopics in one dimension, which the model allows.
    { coordinate: { Barrier: ['Cost', 'Hesitancy'], Setting: ['Facility'], Design: ['Trial'] } },
  ],
}

describe('buildGrid', () => {
  it('counts evidence into cells, and lets one item land in two of them', () => {
    const grid = buildGrid(MAP)
    expect(grid.rows).toEqual(['Cost', 'Hesitancy'])
    expect(grid.cells).toEqual([
      [2, 1],
      [0, 1],
    ])
    expect(grid.placed).toBe(3)
  })

  it('filters by the third dimension without changing the facet counts', () => {
    const grid = buildGrid(MAP, { facet: 'Trial' })
    expect(grid.cells).toEqual([
      [1, 1],
      [0, 1],
    ])
    expect(grid.facets).toEqual([
      { name: 'Trial', count: 2 },
      { name: 'Qualitative', count: 1 },
    ])
  })

  it('returns nothing rather than throwing when there is no map', () => {
    expect(buildGrid(null)).toBeNull()
  })

  it('lets any two dimensions be the axes, and makes the third the facet', () => {
    const grid = buildGrid(MAP, { row: 2, col: 0 })
    expect(grid.rowDim.name).toBe('Design')
    expect(grid.colDim.name).toBe('Barrier')
    expect(grid.facetDim.name).toBe('Setting')
    expect(grid.rows).toEqual(['Trial', 'Qualitative'])
    // Trial: two items, both Cost; one of them is also Hesitancy.
    expect(grid.cells).toEqual([
      [2, 1],
      [1, 0],
    ])
  })

  it('refuses to put the same dimension on both axes', () => {
    expect(buildGrid(MAP, { row: 1, col: 1 })).toBeNull()
  })

  it('reports the whole placed total separately from the filtered one', () => {
    const grid = buildGrid(MAP, { facet: 'Trial' })
    expect(grid.placed).toBe(2)
    expect(grid.total).toBe(3)
  })
})

describe('nextToStart', () => {
  const rows = (states) =>
    states.map(([type, state, hasOperation]) => ({
      type,
      state,
      operation: hasOperation ? { id: `op-${type}` } : undefined,
    }))

  it('queues the first step of a session where nothing has run', () => {
    expect(nextToStart(rows([['enhance_sparse_query', 'todo', false], ['retrieve_sparse_evidence', 'todo', false]])))
      .toBe('enhance_sparse_query')
  })

  it('queues the next step once the one before it finishes', () => {
    expect(nextToStart(rows([['enhance_sparse_query', 'done', true], ['retrieve_sparse_evidence', 'todo', false]])))
      .toBe('retrieve_sparse_evidence')
  })

  it('starts nothing while a step is running or waiting on an answer', () => {
    expect(nextToStart(rows([['enhance_sparse_query', 'running', true], ['retrieve_sparse_evidence', 'todo', false]]))).toBeNull()
    expect(nextToStart(rows([['enhance_sparse_query', 'ask', true], ['retrieve_sparse_evidence', 'todo', false]]))).toBeNull()
  })

  it('leaves a failed step alone, because retrying is the user’s call', () => {
    expect(nextToStart(rows([['enhance_sparse_query', 'failed', true], ['retrieve_sparse_evidence', 'todo', false]]))).toBeNull()
  })

  it('starts nothing once every step is done', () => {
    expect(nextToStart(rows([['enhance_sparse_query', 'done', true]]))).toBeNull()
  })
})


describe('mapIsReady', () => {
  const rows = (entries) => entries.map(([type, state]) => ({ type, state }))

  it('is ready when the agreed-dimensions mapping finishes', () => {
    expect(mapIsReady(rows([['generate_map', 'done']]))).toBe(true)
  })

  it('is ready when the taxonomy mapping finishes instead', () => {
    // Different step, same artifact and coordinates — the map view is agnostic.
    expect(mapIsReady(rows([['generate_taxonomy_map', 'done']]))).toBe(true)
  })

  it('is not ready while mapping is still running', () => {
    expect(mapIsReady(rows([['generate_map', 'running']]))).toBe(false)
  })
})


describe('the mapping branch', () => {
  const session = { params: {} }
  const done = (type) => operation(type, { status: 'complete', result: {} })

  it('keeps the choice quiet until everything before it is done', () => {
    const rows = steps({
      session,
      operations: [operation('screen_evidence', { status: 'running' })],
    })
    const last = rows[rows.length - 1]
    expect(last.type).toBe(MAP_BRANCH)
    expect(last.state).toBe('todo')
    expect(last.branch).toBeNull()
  })

  it('ends the thread on a choice while no mapping tail has been started', () => {
    const rows = steps({
      session,
      operations: ['enhance_sparse_query', 'retrieve_sparse_evidence', 'generate_concept_filters',
        'retrieve_concept_evidence', 'generate_screening_criteria', 'screen_evidence'].map(done),
    })
    const last = rows[rows.length - 1]
    expect(last.type).toBe(MAP_BRANCH)
    expect(last.state).toBe('ask')
    expect(Object.keys(last.branch)).toEqual(['suggested', 'taxonomy'])
  })

  it('will not queue anything past the choice', () => {
    const rows = steps({ session, operations: [done('screen_evidence')] })
    // Everything before it is done, so without the guard this would start a step.
    expect(nextToStart(rows.filter((row) => row.state === 'done' || row.branch))).toBeNull()
  })

  it('replaces the choice with the chosen tail once one is started', () => {
    const rows = steps({
      session,
      operations: [done('screen_evidence'), operation('generate_taxonomy_map', { status: 'running' })],
    })
    expect(rows.some((row) => row.type === MAP_BRANCH)).toBe(false)
    expect(rows[rows.length - 1].type).toBe('generate_taxonomy_map')
    expect(rows.some((row) => row.type === 'generate_map_dimensions')).toBe(false)
  })
})
