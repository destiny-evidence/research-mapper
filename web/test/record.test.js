import { describe, expect, it, vi } from 'vitest'
import { buildRecord } from '../src/record.js'

const client = (overrides = {}) => ({
  getSession: vi.fn(async () => ({ id: 's1', artifacts: { search_queries: 2, dimensions: 1 } })),
  listOperationIds: vi.fn(async () => ['o1', 'o2']),
  getOperation: vi.fn(async (id) => ({ id, decisions: [] })),
  getArtifact: vi.fn(async (_id, type) => ({ type, version: 1, payload: { type } })),
  getMap: vi.fn(async () => ({ dimensions: [], mapped_evidence: [] })),
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
