import { describe, expect, it } from 'vitest'
import { buildGrid, byType, diffChoice, stateOf, steps, summarise } from '../src/derive.js'

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

  it('names the attempt count on a failure', () => {
    expect(summarise(operation('generate_concept_filters', { status: 'failed', attempt: 2 }))).toBe(
      'failed after 2 attempts',
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
  it('attaches every open decision on an operation, not just the first', () => {
    const asking = operation('generate_map_subtopics', { status: 'awaiting_input' })
    const rows = steps({
      session: { params: {} },
      operations: [asking],
      decisions: [
        { id: 1, operation_id: asking.id, answer: null },
        { id: 2, operation_id: asking.id, answer: null },
        { id: 3, operation_id: asking.id, answer: [{ name: 'done' }] },
      ],
    })
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
    const grid = buildGrid(MAP, 'Trial')
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
})
