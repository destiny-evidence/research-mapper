// Bearer auth is a switch on the API: off unless MAPPER_AUTH_ISSUER and
// MAPPER_AUTH_CLIENT_ID are set. Until Keycloak is wired up this sends nothing,
// which is what local development wants.

let token = null

export function setToken(value) {
  token = value
}

export function authHeaders() {
  return token ? { authorization: `Bearer ${token}` } : {}
}
