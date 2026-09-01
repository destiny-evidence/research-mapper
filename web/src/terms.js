// Whether this user has accepted the terms. Stored browser-local.

const KEY = "research-mapper.terms";

// Bump when the terms change materially, so everyone is asked again.
export const TERMS_VERSION = 1;

/**
 * Development overrides.
 * VITE_TERMS=always pins the modal open on every load, for working on it.
 * VITE_TERMS=never suppresses the gate entirely, for working on everything
 * else.
 */
const OVERRIDE = import.meta.env?.VITE_TERMS ?? null;

export function accepted() {
  if (OVERRIDE === "always") return false;
  if (OVERRIDE === "never") return true;
  try {
    return Number(window.localStorage.getItem(KEY)) === TERMS_VERSION;
  } catch {
    return false;
  }
}

export function accept() {
  if (OVERRIDE) return;
  try {
    window.localStorage.setItem(KEY, String(TERMS_VERSION));
  } catch {
    // Not being able to remember the answer is not a reason to block the user.
  }
}
