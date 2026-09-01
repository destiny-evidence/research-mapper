import { describe, expect, it } from 'vitest'
import {
  authorLine,
  cellKey,
  filterReferences,
  foundBy,
  inCell,
  stageCounts,
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

describe('stageCounts', () => {
  it('counts in pipeline order and leaves out the stages nothing reached', () => {
    const counts = stageCounts([
      reference('excluded'),
      reference('mapped'),
      reference('excluded'),
    ])
    expect(counts).toEqual([
      { stage: 'excluded', count: 2 },
      { stage: 'mapped', count: 1 },
    ])
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

  it('narrows to one stage', () => {
    expect(filterReferences(all, { stage: 'excluded' })).toEqual([all[1]])
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
