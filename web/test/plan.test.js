import { describe, expect, it } from 'vitest'
import { planFor, titleOf } from '../src/plan.js'

describe('planFor', () => {
  it('runs both retrieval paths by default, nine steps', () => {
    expect(planFor().map((step) => step.type)).toEqual([
      'enhance_sparse_query',
      'retrieve_sparse_evidence',
      'generate_concept_filters',
      'retrieve_concept_evidence',
      'generate_screening_criteria',
      'screen_evidence',
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

  it('swaps the mapping tail when mapMode is taxonomy', () => {
    const types = planFor({ mapMode: 'taxonomy' }).map((step) => step.type)
    expect(types).toContain('generate_taxonomy_map')
    expect(types).not.toContain('generate_map')
  })

  it('falls back to the raw type for a step it does not know', () => {
    expect(titleOf('something_new')).toBe('something_new')
  })
})
