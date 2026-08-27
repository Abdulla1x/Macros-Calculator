// Guarded localStorage access.
//
// Every read and write in this app goes through here because localStorage is
// not reliably available: Safari's private mode throws on write, and a browser
// set to block site data throws on read too. Neither is an error worth
// surfacing -- everything stored here is a per-device UI preference, so the
// right behaviour is to carry on as though nothing had been remembered.
//
// Hoisted out of lib/dismissals.ts, which had the only copy of this pair until
// the quick-log needed to remember recently used templates as well. Two copies
// of a try/catch this easy to get subtly wrong is one too many.

export function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* The preference just won't stick. */
  }
}
