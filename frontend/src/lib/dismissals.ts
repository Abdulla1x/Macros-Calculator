// Which notices this device has already seen. Per-device rather than per-account
// on purpose: it's a UI preference, not user data, and it needs no table and no
// request. localStorage access is wrapped because Safari's private mode throws
// on write — a failed dismissal should re-show a note, never break the page.

const SEEN_KEY = 'macros_seen_announcements'
const BANNER_KEY = 'macros_dismissed_banner'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* dismissal just won't stick */
  }
}

export function seenAnnouncementIds(): string[] {
  const raw = read(SEEN_KEY)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

/** Has this device ever recorded a dismissal at all?
 *
 * Distinct from `seenAnnouncementIds().length === 0`, which cannot tell a brand
 * new device from one that has dismissed nothing: absence of the key means both.
 * That distinction is the whole reason the first-run modal could not be capped
 * safely -- capping the display while the fetch still returns every note turns
 * onboarding into dismiss-three-reload-repeat.
 *
 * NOTE `read` returns null both when the key is absent AND when localStorage
 * throws, which it does in Safari private mode. That browser therefore reads as
 * "first run" on every load: it sees the welcome each time and never the full
 * backlog. That is the safe direction to fail in, and it is deliberate. */
export function hasEverSeenAnnouncements(): boolean {
  return read(SEEN_KEY) !== null
}

export function markAnnouncementsSeen(ids: string[]) {
  const merged = new Set([...seenAnnouncementIds(), ...ids])
  write(SEEN_KEY, JSON.stringify([...merged]))
}

// Keyed by the banner's own text: editing the notice in the hosting dashboard
// makes it a new notice, which should reappear even for someone who dismissed
// the last one.
export function isBannerDismissed(banner: string): boolean {
  return read(BANNER_KEY) === banner
}

export function dismissBanner(banner: string) {
  write(BANNER_KEY, banner)
}
