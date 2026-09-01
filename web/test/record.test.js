import { describe, expect, it, vi } from 'vitest'
import { buildRecord } from '../src/record.js'

const client = (overrides = {}) => ({
  getSession: vi.fn(async () => ({ id: 's1', artifacts: { search_queries: 2, dimensions: 1 } })),
  listOperationIds: vi.fn(async () => ['o1', 'o2']),
  getOperation: vi.fn(async (id) => ({ id, decisions: [] })),
  getArtifact: vi.fn(async (_id, type) => ({ type, version: 1, payload: { type } })),
  getMap: vi.fn(async () => ({
    dimensions: [],
    mapped_evidence: [{ evidence: { destiny_id: 'r1' }, coordinate: { Setting: ['Urban'] } }],
  })),
  listReferences: vi.fn(async (_id, options) => [
    {
      destiny_id: 'r1',
      stage: 'excluded',
      screening: { include: false, reasoning: 'high-income only' },
      evidence: options?.includeEvidence ? { title: 'Barriers in Kenya' } : null,
    },
  ]),
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

  it('names each reference, so the record reads without the repository', async () => {
    const record = await buildRecord('s1', client())
    expect(record.references[0].evidence.title).toBe('Barriers in Kenya')
  })

  it('joins the map to the references rather than hydrating it twice', async () => {
    const stub = client()
    const record = await buildRecord('s1', stub)

    expect(stub.getMap).toHaveBeenCalledWith('s1', { includeEvidence: false })
    expect(record.map.mapped_evidence[0].evidence.title).toBe('Barriers in Kenya')
    expect(record.map.mapped_evidence[0].coordinate).toEqual({ Setting: ['Urban'] })
  })

  it('leaves the map’s ids alone when the references could not be fetched', async () => {
    const stub = client({
      listReferences: vi.fn(async () => {
        throw new Error('repository down')
      }),
    })
    const record = await buildRecord('s1', stub)
    expect(record.map.mapped_evidence[0].evidence).toEqual({ destiny_id: 'r1' })
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
