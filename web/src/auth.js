// Keycloak sign-in, and the bearer token every API call carries.
//
// Configured or not is the same switch the API uses: it accepts anonymous
// requests unless MAPPER_AUTH_ISSUER and MAPPER_AUTH_CLIENT_ID are both set,
// and this sends no token unless the VITE_KEYCLOAK_* triple is set. Local
// development sets neither and nothing here runs.

import Keycloak from 'keycloak-js'

// How much validity a token must have left to be worth reusing. Below this it
// is renewed before the call rather than after a 401.
const MIN_VALIDITY_SECONDS = 30

// Where the app was heading before it was bounced to Keycloak. Session-scoped
// because it is only meaningful for the round trip that is in flight.
const ROUTE_KEY = 'research-mapper.route'

const env = import.meta.env ?? {}

export const config = {
  url: env.VITE_KEYCLOAK_URL,
  realm: env.VITE_KEYCLOAK_REALM,
  clientId: env.VITE_KEYCLOAK_CLIENT_ID,
}

export const configured = Boolean(config.url && config.realm && config.clientId)

let keycloak = null

/** Read and clear the stashed route, if there is one. */
function takeRoute() {
  try {
    const route = window.sessionStorage.getItem(ROUTE_KEY)
    window.sessionStorage.removeItem(ROUTE_KEY)
    return route
  } catch {
    return null
  }
}

function stashRoute(route) {
  try {
    window.sessionStorage.setItem(ROUTE_KEY, route)
  } catch {
    // Losing the deep link is a worse landing page, not a broken sign-in.
  }
}

/**
 * Signs in, redirecting to Keycloak if the browser has no session. Resolves
 * once there is a token, so nothing renders before there is a user.
 */
export async function login() {
  if (!configured) return
  keycloak = new Keycloak(config)

  // keycloak-js defaults the redirect URI to location.href verbatim, and an
  // OAuth redirect URI may carry no fragment (RFC 6749 §3.1.2) — which is
  // exactly where this app keeps its route. So the redirect URI is the bare
  // page, and the route goes to sessionStorage to be restored below.
  const { origin, pathname, hash } = window.location
  if (hash) stashRoute(hash)

  await keycloak.init({
    onLoad: 'login-required',
    redirectUri: origin + pathname,
    pkceMethod: 'S256',
    // Pairs with the above: the default fragment response mode would come back
    // with the auth code sitting where the route lives.
    responseMode: 'query',
    // The check-session iframe is third-party-cookie territory and browsers
    // increasingly refuse it. updateToken covers expiry on its own.
    checkLoginIframe: false,
  })

  // Set before anything renders, so the app reads the intended route first
  // time rather than flashing the session list and then moving.
  const route = takeRoute()
  if (route && route !== window.location.hash) window.location.hash = route
}

/**
 * The Authorization header for one request, renewing the token first if it is
 * close to expiring. `{}` when Keycloak is not configured.
 */
export async function authHeaders() {
  if (!keycloak) return {}
  try {
    await keycloak.updateToken(MIN_VALIDITY_SECONDS)
  } catch {
    // The refresh token is gone or rejected. There is nothing to retry with,
    // so send the user back through sign-in rather than letting every call 401.
    await keycloak.login()
    return {}
  }
  return { authorization: `Bearer ${keycloak.token}` }
}

export function logout() {
  if (keycloak) keycloak.logout()
}

/** The signed-in user, for the chrome to show who is looking. */
export function profile() {
  const claims = keycloak?.tokenParsed
  if (!claims) return null
  return { name: claims.name || claims.preferred_username, email: claims.email }
}

/** Test seam: installs a stand-in for the Keycloak adapter. */
export function useAdapter(stub) {
  keycloak = stub
}
