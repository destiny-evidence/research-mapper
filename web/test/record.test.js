import { describe, expect, it, vi } from 'vitest'
import { buildRecord } from '../src/record.js'

const client = (overrides = {}) => ({
  getSession: vi.fn(async () => ({ id: 's1', artifacts: { search_queries: 2, dimensions: 1 } })),
  listOperationIds: vi.fn(async () => ['o1', 'o2']),
  getOperation: vi.fn(async (id) => ({ id, decisions: [] })),
  getArtifact: vi.fn(async (_id, type) => ({ type, version: 1, payload: { type } })),
  getMap: vi.fn(async () => ({
    dimensions: [],
    cells: [{ coordinate: { Setting: ['Urban'] }, count: 1 }],
    total: 1,
  })),
  listReferences: vi.fn(async () => ({
    items: [
      {
        destiny_id: 'r1',
        stage: 'excluded',
        screening: { include: false, reasoning: 'high-income only' },
        evidence: null,
      },
    ],
    next: null,
  })),
  ...overrides,
})

describe('buildRecord', () => {
  it('fetches every operation and every artifact the session lists', async () => {
    const stub = client()
    const record = await buildRecord('s1', stub)

    expect(stub.getOperation).toHaveBeenCalledTimes(2)
    expect(stub.getArtifact.mock.calls.map(([, type]) => type)).toEqual([
      'search_queries',
      'dimensions',
    ])
    expect(Object.keys(record.artifacts)).toEqual(['search_queries', 'dimensions'])
    expect(record.operations).toHaveLength(2)
  })

  it('carries the per-reference reasoning nothing else exposes', async () => {
    const record = await buildRecord('s1', client())
    expect(record.references[0].screening.reasoning).toBe('high-income only')
  })

  it('pages through every reference, without looking any of them up', async () => {
    const pages = {
      null: { items: [{ destiny_id: 'r1' }, { destiny_id: 'r2' }], next: 'r2' },
      r2: { items: [{ destiny_id: 'r3' }], next: null },
    }
    const stub = client({
      listReferences: vi.fn(async (_id, { after }) => pages[after]),
    })
    const record = await buildRecord('s1', stub)

    expect(record.references.map((r) => r.destiny_id)).toEqual(['r1', 'r2', 'r3'])
    for (const [, options] of stub.listReferences.mock.calls)
      expect(options.includeEvidence).toBeFalsy()
  })

  it('still builds when the references could not be fetched', async () => {
    const stub = client({
      listReferences: vi.fn(async () => {
        throw new Error('database down')
      }),
    })
    const record = await buildRecord('s1', stub)
    expect(record.references).toEqual([])
  })

  it('carries the map as its counts per coordinate', async () => {
    const stub = client()
    const record = await buildRecord('s1', stub)

    expect(stub.getMap).toHaveBeenCalledWith('s1')
    expect(record.map.cells).toEqual([{ coordinate: { Setting: ['Urban'] }, count: 1 }])
  })

  it('is fine with a session that has no map yet, which is most of its life', async () => {
    const stub = client({ getMap: vi.fn(async () => { throw new Error('no map yet') }) })
    const record = await buildRecord('s1', stub)
    expect(record.map).toBeNull()
  })

  it('handles a session with no artifacts at all', async () => {
    const stub = client({ getSession: vi.fn(async () => ({ id: 's1' })) })
    const record = await buildRecord('s1', stub)
    expect(record.artifacts).toEqual({})
  })
})
