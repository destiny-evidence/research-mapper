import { describe, expect, it, beforeEach } from 'vitest'
import { authHeaders, configured, profile, useAdapter } from '../src/auth.js'

/** A stand-in for the Keycloak adapter, recording what was asked of it. */
const adapter = (overrides = {}) => ({
  token: 'a-token',
  tokenParsed: { preferred_username: 'ada', email: 'ada@example.org' },
  updateToken: async () => false,
  login: async () => {},
  ...overrides,
})

beforeEach(() => useAdapter(null))

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
  it('is off without the VITE_KEYCLOAK_* triple, as in development', () => {
    expect(configured).toBe(false)
  })
})

describe('login', () => {
  it('does nothing when Keycloak is not configured', async () => {
    // Development: no VITE_KEYCLOAK_* triple, so no redirect and no token.
    const { login } = await import('../src/auth.js')
    await login()
    expect(await authHeaders()).toEqual({})
  })
})

