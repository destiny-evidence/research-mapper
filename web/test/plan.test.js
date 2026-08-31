import { describe, expect, it } from 'vitest'
import { MAP_TAILS, planFor, tailOf, titleOf } from '../src/plan.js'

describe('planFor', () => {
  it('stops short of the map until a mapping tail is started', () => {
    expect(planFor().map((step) => step.type)).toEqual([
      'enhance_sparse_query',
      'retrieve_sparse_evidence',
      'generate_concept_filters',
      'retrieve_concept_evidence',
      'generate_screening_criteria',
      'screen_evidence',
    ])
  })

  it('adds the suggested-dimensions tail once it is chosen', () => {
    expect(planFor({}, 'suggested').map((step) => step.type).slice(-3)).toEqual([
      'generate_map_dimensions',
      'generate_map_subtopics',
      'generate_map',
    ])
  })

  it('puts concept filtering before screening, not after', () => {
    const order = planFor().map((step) => step.type)
    expect(order.indexOf('generate_concept_filters')).toBeLessThan(order.indexOf('screen_evidence'))
  })

  it('drops the taxonomy path when the session only searches by query', () => {
    const types = planFor({ mode: 'sparse' }).map((step) => step.type)
    expect(types).not.toContain('generate_concept_filters')
    expect(types).toContain('enhance_sparse_query')
  })

  it('takes the taxonomy tail instead, which is a single step', () => {
    const types = planFor({}, 'taxonomy').map((step) => step.type)
    expect(types).toContain('generate_taxonomy_map')
    expect(types).not.toContain('generate_map')
    expect(types).not.toContain('generate_map_dimensions')
  })

  it('falls back to the raw type for a step it does not know', () => {
    expect(titleOf('something_new')).toBe('something_new')
  })
})


describe('tailOf', () => {
  const ops = (types) => types.map((type) => ({ type }))

  it('is nothing until a mapping step has been started', () => {
    expect(tailOf(ops(['screen_evidence']))).toBeNull()
  })

  it('reads the choice off whichever tail was started, which is the only record of it', () => {
    expect(tailOf(ops(['screen_evidence', 'generate_map_dimensions']))).toBe('suggested')
    expect(tailOf(ops(['screen_evidence', 'generate_taxonomy_map']))).toBe('taxonomy')
  })

  it('names a head for every tail it offers', () => {
    for (const tail of Object.values(MAP_TAILS)) {
      expect(planFor({}, 'suggested').concat(planFor({}, 'taxonomy')).map((s) => s.type)).toContain(
        tail.head,
      )
    }
  })
})
