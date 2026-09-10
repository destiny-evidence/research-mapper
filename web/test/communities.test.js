import { describe, expect, it } from 'vitest'
import {
  COMMUNITIES,
  communityLabel,
  communityLevel,
  communityName,
  communitySlug,
} from '../src/communities.js'

describe('communities', () => {
  it('offers destiny at high recall first, which a new session defaults to', () => {
    expect(COMMUNITIES[0]).toBe('destiny_high_recall')
  })

  it('files every destiny threshold under the one repository path', () => {
    const destiny = COMMUNITIES.filter((c) => c.startsWith('destiny'))
    expect(destiny).toHaveLength(3)
    expect(destiny.map(communitySlug)).toEqual(['destiny', 'destiny', 'destiny'])
  })

  it('names the threshold, so two destiny sessions are tellable apart', () => {
    expect(communityLabel('destiny_high_recall')).toBe('DESTINY (high recall)')
    expect(communityLabel('destiny_balanced')).toBe('DESTINY (balanced)')
    expect(communityLabel('destiny_high_precision')).toBe(
      'DESTINY (high precision)',
    )
  })

  it('leaves a community with only one threshold unqualified', () => {
    expect(communityLabel('hpv')).toBe('HPV')
    expect(communityName('hpv')).toBe('HPV')
    expect(communityLevel('hpv')).toBe(null)
  })

  it('shouts an unknown community rather than rendering nothing', () => {
    expect(communityLabel('cdr')).toBe('CDR')
    expect(communityName('cdr')).toBe('CDR')
    expect(communitySlug('cdr')).toBe('cdr')
    expect(communityLevel('cdr')).toBe(null)
  })

  it('matches case-insensitively, as a stored community may come back shouted', () => {
    expect(communitySlug('DESTINY_BALANCED')).toBe('destiny')
    expect(communityLabel('ESEA')).toBe('ESEA')
  })
})
