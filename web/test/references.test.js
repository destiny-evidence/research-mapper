import { describe, expect, it } from 'vitest'
import {
  authorLine,
  cellKey,
  decisionLabel,
  foundBy,
  placementOf,
  referenceStamp,
  UNPLACED,
  unplacedBecause,
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

describe('unplacedBecause', () => {
  const included = (extra = {}) =>
    reference('included', { screening: { include: true }, ...extra })

  it('has nothing to explain about a reference that is on the map', () => {
    expect(unplacedBecause(MAPPED)).toBe(null)
  })

  it('has nothing to explain about a reference screening left out', () => {
    const out = reference('excluded', { screening: { include: false } })
    expect(unplacedBecause(out)).toBe(null)
  })

  it('blames the missing record when the repository returned none', () => {
    expect(unplacedBecause(included())).toBe(UNPLACED.missing)
  })

  it('blames the model when the reference had everything it needed', () => {
    expect(unplacedBecause(included({ evidence: { title: 'A trial' } }))).toBe(
      UNPLACED.unplaced,
    )
  })

  it('blames the annotations on a taxonomy map, not the model', () => {
    const bare = included({ evidence: { title: 'A trial', known_concepts: [] } })
    expect(unplacedBecause(bare, 'taxonomy')).toBe(UNPLACED.unannotated)

    const partial = included({
      evidence: { title: 'A trial', known_concepts: ['https://vocab/1'] },
    })
    expect(unplacedBecause(partial, 'taxonomy')).toBe(UNPLACED.partial)
  })

  it('reports a reference the run could not process at all', () => {
    expect(unplacedBecause(reference('failed'))).toBe(UNPLACED.failed)
  })
})

describe('decisionLabel', () => {
  it('says a dedicated decision model is one', () => {
    const decision = { model: 'gpt-6-luna', dedicated: true }
    expect(decisionLabel(decision)).toBe('gpt-6-luna · dedicated decision model')
    expect(decisionLabel(decision, { short: true })).toBe('gpt-6-luna (decision model)')
  })

  it('says outright when the chat model stood in', () => {
    const decision = { model: 'gpt-chat', dedicated: false }
    expect(decisionLabel(decision)).toBe(
      'gpt-chat · chat model (no decision model configured, probabilities self-reported)',
    )
    expect(decisionLabel(decision, { short: true })).toBe('gpt-chat (chat model)')
  })

  it('names just the model on records made before the kind was stored', () => {
    expect(decisionLabel({ model: 'gpt-6-luna' })).toBe('gpt-6-luna')
    expect(decisionLabel({ model: 'gpt-6-luna' }, { short: true })).toBe('gpt-6-luna')
  })
})
