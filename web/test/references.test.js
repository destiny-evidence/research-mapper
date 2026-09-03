import { describe, expect, it } from 'vitest'
import {
  authorLine,
  bucketCounts,
  cellKey,
  filterReferences,
  foundBy,
  inCell,
  placementOf,
  referencesFor,
  referenceStamp,
  SLICES,
  verdictOf,
} from '../src/derive.js'

const reference = (stage, extra = {}) => ({
  destiny_id: `r-${stage}`,
  stage,
  provenance: [],
  screening: null,
  coordinate: null,
  mapping: null,
  evidence: null,
  ...extra,
})

const MAPPED = reference('mapped', {
  coordinate: { Setting: ['Urban'], Outcome: ['Mortality'] },
  mapping: { dimensions_version: 2, reasoning: 'reports both' },
})

describe('bucketCounts', () => {
  it('counts in pipeline order and leaves out the stages nothing reached', () => {
    const counts = bucketCounts([
      reference('excluded'),
      reference('mapped'),
      reference('excluded'),
    ])
    expect(counts).toEqual([
      { bucket: 'excluded', count: 2 },
      { bucket: 'mapped', count: 1 },
    ])
  })

  it('counts a placed reference as included under screening', () => {
    const counts = bucketCounts([MAPPED, reference('excluded')], SLICES.verdict)
    expect(counts).toEqual([
      { bucket: 'included', count: 1 },
      { bucket: 'excluded', count: 1 },
    ])
  })
})

describe('verdictOf', () => {
  it('reads the screening verdict a placed reference still carries', () => {
    expect(verdictOf(MAPPED)).toBe('included')
  })

  it('trusts the recorded verdict over the stage', () => {
    const kept = reference('mapped', { screening: { include: true } })
    expect(verdictOf(kept)).toBe('included')
    const dropped = reference('excluded', { screening: { include: false } })
    expect(verdictOf(dropped)).toBe('excluded')
  })

  it('separates a reference screening has not reached from one it excluded', () => {
    expect(verdictOf(reference('gathered'))).toBe('not screened')
  })
})

describe('placementOf', () => {
  it('borrows the pipeline’s own word, so a row reads the same either way', () => {
    expect(placementOf(reference('included'))).toBe('not mapped')
    expect(placementOf(MAPPED)).toBe('mapped')
  })
})

describe('referenceStamp', () => {
  const row = (type, state, done) => ({
    type,
    state,
    operation: done === undefined ? undefined : { progress: { done } },
  })

  it('changes as a step works through the references', () => {
    const before = referenceStamp([row('screen_evidence', 'running', 100)])
    const after = referenceStamp([row('screen_evidence', 'running', 200)])
    expect(before).not.toBe(after)
  })

  it('changes when a step finishes, which is when the last poll is missed', () => {
    const running = referenceStamp([row('screen_evidence', 'running', 212)])
    const done = referenceStamp([row('screen_evidence', 'done', 212)])
    expect(running).not.toBe(done)
  })

  it('ignores steps that cannot move a reference', () => {
    const rows = [row('generate_map_dimensions', 'running', 2)]
    expect(referenceStamp(rows)).toBe('')
  })
})

describe('referencesFor', () => {
  const sparse = reference('gathered', {
    provenance: [{ mode: 'sparse', query: 'hpv' }],
  })
  const taxonomy = reference('included', {
    provenance: [{ mode: 'taxonomy', filters: [] }],
  })
  const all = [sparse, taxonomy, MAPPED]

  it('narrows a retrieval step to what that retrieval found', () => {
    expect(referencesFor('retrieve_sparse_evidence', all)).toEqual([sparse])
    expect(referencesFor('retrieve_concept_evidence', all)).toEqual([taxonomy])
  })

  it('gives screening the whole list, since it is about all of it', () => {
    expect(referencesFor('screen_evidence', all)).toHaveLength(3)
  })

  it('narrows mapping to what screening kept', () => {
    expect(referencesFor('generate_map', all)).toEqual([taxonomy, MAPPED])
  })

  it('has nothing to show for a step with no table', () => {
    expect(referencesFor('enhance_sparse_query', all)).toBeNull()
    expect(referencesFor('screen_evidence', null)).toBeNull()
  })
})

describe('cellKey', () => {
  it('is the same key however the terms are ordered', () => {
    const one = cellKey([['Setting', 'Urban'], ['Outcome', 'Mortality']])
    const other = cellKey([['Outcome', 'Mortality'], ['Setting', 'Urban']])
    expect(one).toBe(other)
  })

  it('separates a facetted cell from the same cell unfacetted', () => {
    const plain = cellKey([['Setting', 'Urban'], ['Outcome', 'Mortality']])
    const facetted = cellKey([
      ['Setting', 'Urban'],
      ['Outcome', 'Mortality'],
      ['Design', 'Cohort'],
    ])
    expect(plain).not.toBe(facetted)
  })
})

describe('inCell', () => {
  it('needs every term, since a cell is the intersection', () => {
    expect(inCell(MAPPED.coordinate, [['Setting', 'Urban']])).toBe(true)
    expect(
      inCell(MAPPED.coordinate, [['Setting', 'Urban'], ['Outcome', 'Other']]),
    ).toBe(false)
  })

  it('holds for a reference in several subtopics of one dimension', () => {
    const coordinate = { Setting: ['Urban', 'Rural'] }
    expect(inCell(coordinate, [['Setting', 'Rural']])).toBe(true)
  })

  it('is false for a reference with no coordinate at all', () => {
    expect(inCell(null, [['Setting', 'Urban']])).toBe(false)
  })
})

describe('filterReferences', () => {
  const all = [reference('gathered'), reference('excluded'), MAPPED]

  it('returns everything with no filter', () => {
    expect(filterReferences(all)).toHaveLength(3)
  })

  it('narrows to one bucket of the slice it is read through', () => {
    expect(filterReferences(all, { bucket: 'excluded' })).toEqual([all[1]])
    expect(filterReferences(all, { bucket: 'included' }, SLICES.verdict)).toEqual([
      MAPPED,
    ])
  })

  it('narrows to a cell, which only a mapped reference can match', () => {
    const shown = filterReferences(all, { terms: [['Setting', 'Urban']] })
    expect(shown).toEqual([MAPPED])
  })
})

describe('authorLine', () => {
  it('abbreviates past the first author', () => {
    expect(authorLine({ authors: ['Smith', 'Jones'] })).toBe('Smith et al.')
    expect(authorLine({ authors: ['Smith'] })).toBe('Smith')
  })

  it('is empty for a reference that never hydrated', () => {
    expect(authorLine(null)).toBe('')
  })
})

describe('foundBy', () => {
  const GROUPS = [
    {
      scheme: 'Misinformation',
      labels: ['Detection', 'Addressing', 'Legal strategies'],
      concepts: ['http://v/detect', 'http://v/address', 'http://v/legal'],
    },
  ]
  const viaFilters = (knownConcepts) => ({
    provenance: [
      {
        mode: 'taxonomy',
        filters: [{ scheme: 'Misinformation', labels: GROUPS[0].labels }],
      },
    ],
    evidence: { known_concepts: knownConcepts },
  })

  it('keeps the two retrieval modes apart', () => {
    const reference = {
      provenance: [
        { mode: 'sparse', query: 'hpv AND uptake' },
        {
          mode: 'taxonomy',
          filters: [{ scheme: 'Misinformation', labels: GROUPS[0].labels }],
        },
      ],
      evidence: { known_concepts: ['http://v/detect'] },
    }
    expect(foundBy(reference, GROUPS)).toEqual({
      queries: ['hpv AND uptake'],
      concepts: ['Misinformation: Detection'],
    })
  })

  it('names the query for a sparse hit', () => {
    const reference = {
      provenance: [{ mode: 'sparse', query: 'hpv AND uptake' }],
    }
    expect(foundBy(reference)).toEqual({
      queries: ['hpv AND uptake'],
      concepts: [],
    })
  })

  it('collapses a reference the same query found twice', () => {
    const reference = {
      provenance: [
        { mode: 'sparse', query: 'hpv' },
        { mode: 'sparse', query: 'hpv' },
      ],
    }
    expect(foundBy(reference).queries).toEqual(['hpv'])
  })

  it('narrows a filter group to the concepts the reference actually carries', () => {
    const found = foundBy(viaFilters(['http://v/legal', 'http://v/detect']), GROUPS)
    expect(found.concepts).toEqual(['Misinformation: Detection, Legal strategies'])
  })

  it('ignores annotations that are not in the filter', () => {
    const found = foundBy(viaFilters(['http://v/detect', 'http://v/unrelated']), GROUPS)
    expect(found.concepts).toEqual(['Misinformation: Detection'])
  })

  it('names the group as a whole when the reference never hydrated', () => {
    const reference = { ...viaFilters([]), evidence: null }
    expect(foundBy(reference, GROUPS).concepts).toEqual([
      'Misinformation · 3 concepts',
    ])
  })

  it('names the group as a whole without the concept_filters artifact', () => {
    const found = foundBy(viaFilters(['http://v/detect']))
    expect(found.concepts).toEqual(['Misinformation · 3 concepts'])
  })
})
