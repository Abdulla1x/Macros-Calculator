// Where the session token lives, and what happens when the browser refuses to
// keep it.
//
// Every one of these three calls used to touch localStorage unguarded. Safari's
// private mode, Firefox's "block all cookies", and an ordinary browser with
// site data switched off all throw on access rather than returning null — and
// AuthProvider reads the token during its first render, so the throw happened
// before anything was on screen. The result was a white page with no message,
// on a browser the user had configured deliberately.
//
// lib/dismissals.ts wraps localStorage for the same reason and has said so in a
// comment since Phase 2. The difference is the consequence. A dismissal that
// fails to stick re-shows a notice, which is harmless enough to swallow. A
// token that fails to stick means the user signs in, uses the app, closes the
// tab and is silently signed out — so it is kept in memory for the life of the
// page, and the login screen says plainly that it will not outlive the tab.

const TOKEN_KEY = 'macros_token'
const PROBE_KEY = 'macros_storage_probe'

function readStored(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

// The authoritative value for this page's lifetime, seeded from storage at load
// so a normal browser behaves exactly as before. Reads never go back to
// localStorage: if a write failed, storage holds a stale token or none, and
// memory holds the real one.
let memoryToken: string | null = readStored()

export function getToken(): string | null {
  return memoryToken
}

export function setToken(token: string) {
  memoryToken = token
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* Session still works; it just won't survive a reload. */
  }
}

export function clearToken() {
  memoryToken = null
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* Nothing was stored, so there is nothing to remove. */
  }
}

/** Whether a signed-in session will survive closing the tab.
 *
 * Probes with a write rather than reading a flag set by an earlier failure,
 * because the question is asked on the login screen — before there is any token
 * to have failed to store. A read-only check would not do: some browsers allow
 * getItem and throw only on setItem.
 */
export function isSessionPersistent(): boolean {
  try {
    localStorage.setItem(PROBE_KEY, '1')
    localStorage.removeItem(PROBE_KEY)
    return true
  } catch {
    return false
  }
}
