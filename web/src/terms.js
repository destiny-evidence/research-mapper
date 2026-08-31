// Whether this user has accepted the terms.
//
// Browser-local, which is the weak version: clearing site data re-prompts, and
// a shared machine never prompts the second person. The acknowledgement belongs
// server-side against the user once auth is wired up — sessions are already
// scoped to a user, so there is somewhere to put it. Until then this at least
// puts the terms in front of someone before they see an output.

const KEY = 'research-mapper.terms'

// Bump when the terms change materially, so everyone is asked again.
export const TERMS_VERSION = 1

/**
 * VITE_TERMS=always pins the modal open on every load, for working on it.
 * VITE_TERMS=never suppresses the gate entirely, for working on everything
 * else. Neither touches what is stored, so unsetting it puts you back where you
 * were. Development only: nothing sets this in the deployed build, and if
 * something ever does, `never` silently removes the only point at which a user
 * is told what the tool is.
 */
const OVERRIDE = import.meta.env?.VITE_TERMS ?? null

export function accepted() {
  if (OVERRIDE === 'always') return false
  if (OVERRIDE === 'never') return true
  try {
    return Number(window.localStorage.getItem(KEY)) === TERMS_VERSION
  } catch {
    // Private browsing and locked-down profiles throw rather than return null.
    return false
  }
}

export function accept() {
  if (OVERRIDE) return
  try {
    window.localStorage.setItem(KEY, String(TERMS_VERSION))
  } catch {
    // Not being able to remember the answer is not a reason to block the user.
  }
}
