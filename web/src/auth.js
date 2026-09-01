import Keycloak from "keycloak-js";

const MIN_VALIDITY_SECONDS = 30;

const ROUTE_KEY = "research-mapper.route";

const env = import.meta.env ?? {};

export const config = {
  url: env.VITE_KEYCLOAK_URL,
  realm: env.VITE_KEYCLOAK_REALM,
  clientId: env.VITE_KEYCLOAK_CLIENT_ID,
};

export const configured = Boolean(
  config.url && config.realm && config.clientId,
);

let keycloak = null;

/** Read and clear the stashed route, if there is one. */
function takeRoute() {
  try {
    const route = window.sessionStorage.getItem(ROUTE_KEY);
    window.sessionStorage.removeItem(ROUTE_KEY);
    return route;
  } catch {
    return null;
  }
}

function stashRoute(route) {
  try {
    window.sessionStorage.setItem(ROUTE_KEY, route);
  } catch {
    // Losing the deep link is a worse landing page, not a broken sign-in.
  }
}

/** Signs in, redirecting to Keycloak if the browser has no session. */
export async function login() {
  if (!configured) return;
  keycloak = new Keycloak(config);

  const { origin, pathname, hash } = window.location;
  if (hash) stashRoute(hash);

  await keycloak.init({
    onLoad: "login-required",
    redirectUri: origin + pathname,
    pkceMethod: "S256",
    responseMode: "query",
    checkLoginIframe: false,
  });

  const route = takeRoute();
  if (route && route !== window.location.hash) window.location.hash = route;
}

/**
 * The Authorization header for one request, renewing the token first if it is
 * close to expiring. `{}` when Keycloak is not configured.
 */
export async function authHeaders() {
  if (!keycloak) return {};
  try {
    await keycloak.updateToken(MIN_VALIDITY_SECONDS);
  } catch {
    await keycloak.login();
    return {};
  }
  return { authorization: `Bearer ${keycloak.token}` };
}

export function logout() {
  if (keycloak) keycloak.logout();
}

/** The signed-in user. */
export function profile() {
  const claims = keycloak?.tokenParsed;
  if (!claims) return null;
  return {
    name: claims.name || claims.preferred_username,
    email: claims.email,
  };
}

/** Test seam: installs a stand-in for the Keycloak adapter. */
export function useAdapter(stub) {
  keycloak = stub;
}
