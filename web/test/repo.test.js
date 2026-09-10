import { afterEach, describe, expect, it, vi } from 'vitest'

const load = async (env) => {
  vi.resetModules()
  vi.stubEnv('VITE_DESTINY_ENV', env)
  return import('../src/repo.js')
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('referenceUrl', () => {
  it('leaves production on the bare host, as destiny_sdk does', async () => {
    const { referenceUrl } = await load('production')
    expect(referenceUrl('HPV', 'abc')).toBe(
      'https://data.evidence-repository.org/hpv/references/abc',
    )
  })

  it('segments staging', async () => {
    const { referenceUrl } = await load('staging')
    expect(referenceUrl('esea', 'abc')).toBe(
      'https://data.staging.evidence-repository.org/esea/references/abc',
    )
  })

  it('shortens development to dev, as destiny_sdk does', async () => {
    const { referenceUrl } = await load('development')
    expect(referenceUrl('hpv', 'abc')).toBe(
      'https://data.dev.evidence-repository.org/hpv/references/abc',
    )
  })

  it('leaves an unknown environment visibly wrong, not pointed at production', async () => {
    const { referenceUrl } = await load('sandbox')
    expect(referenceUrl('hpv', 'abc')).toContain('data.sandbox.')
  })

  it('defaults to production when the build sets nothing', async () => {
    const { referenceUrl } = await load(undefined)
    expect(referenceUrl('hpv', 'abc')).toContain(
      'https://data.evidence-repository.org/',
    )
  })
})
