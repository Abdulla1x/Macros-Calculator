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
