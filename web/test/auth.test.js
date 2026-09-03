import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { authHeaders, profile, useAdapter } from '../src/auth.js'

/** A stand-in for the Keycloak adapter, recording what was asked of it. */
const adapter = (overrides = {}) => ({
  token: 'a-token',
  tokenParsed: { preferred_username: 'ada', email: 'ada@example.org' },
  updateToken: async () => false,
  login: async () => {},
  ...overrides,
})

beforeEach(() => useAdapter(null))
afterEach(() => vi.unstubAllEnvs())

const TRIPLE = {
  VITE_KEYCLOAK_URL: 'https://keycloak.example.org',
  VITE_KEYCLOAK_REALM: 'destiny',
  VITE_KEYCLOAK_CLIENT_ID: 'research-mapper',
}

const NONE = Object.fromEntries(Object.keys(TRIPLE).map((key) => [key, undefined]))

/**
 * Re-import auth.js under a stated environment. `configured` is read once at
 * import, so a test that does not say what the environment is inherits the
 * developer's own .env and passes or fails according to whose machine it is on.
 */
async function withEnv(vars) {
  vi.resetModules()
  for (const [key, value] of Object.entries(vars)) vi.stubEnv(key, value)
  return import('../src/auth.js')
}

describe('authHeaders', () => {
  it('sends nothing until Keycloak has signed the user in', async () => {
    expect(await authHeaders()).toEqual({})
  })

  it('carries the current token', async () => {
    useAdapter(adapter())
    expect(await authHeaders()).toEqual({ authorization: 'Bearer a-token' })
  })

  it('renews an expiring token before the call, not after a 401', async () => {
    let renewed = false
    const kc = adapter({
      updateToken: async () => {
        renewed = true
        kc.token = 'renewed'
        return true
      },
    })
    useAdapter(kc)
    expect(await authHeaders()).toEqual({ authorization: 'Bearer renewed' })
    expect(renewed).toBe(true)
  })

  it('sends the user back through sign-in when the refresh is rejected', async () => {
    let signedIn = false
    useAdapter(
      adapter({
        updateToken: async () => {
          throw new Error('invalid_grant')
        },
        login: async () => {
          signedIn = true
        },
      }),
    )
    // No stale token: the header would only earn a 401.
    expect(await authHeaders()).toEqual({})
    expect(signedIn).toBe(true)
  })
})

describe('profile', () => {
  it('is null when nobody is signed in', () => {
    expect(profile()).toBe(null)
  })

  it('reads the name and email off the token', () => {
    useAdapter(adapter())
    expect(profile()).toEqual({ name: 'ada', email: 'ada@example.org' })
  })

  it('falls back to the username when the token carries no name', () => {
    useAdapter(adapter({ tokenParsed: { preferred_username: 'ada' } }))
    expect(profile().name).toBe('ada')
  })
})

describe('configured', () => {
  it('is off without the VITE_KEYCLOAK_* triple, as in development', async () => {
    expect((await withEnv(NONE)).configured).toBe(false)
  })

  it('is on with all three', async () => {
    expect((await withEnv(TRIPLE)).configured).toBe(true)
  })

  it('is off with only part of the triple, rather than half-configured', async () => {
    const partial = { ...TRIPLE, VITE_KEYCLOAK_CLIENT_ID: undefined }
    expect((await withEnv(partial)).configured).toBe(false)
  })
})

describe('login', () => {
  it('does nothing when Keycloak is not configured', async () => {
    // No triple, so no redirect and no token.
    const auth = await withEnv(NONE)
    await auth.login()
    expect(await auth.authHeaders()).toEqual({})
  })
})

