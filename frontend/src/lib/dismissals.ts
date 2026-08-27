// Which notices this device has already seen. Per-device rather than per-account
// on purpose: it's a UI preference, not user data, and it needs no table and no
// request. Reads and writes go through lib/storage, which swallows the throw
// Safari's private mode raises — a failed dismissal should re-show a note, never
// break the page.

import { readLocal, writeLocal } from './storage'

const SEEN_KEY = 'macros_seen_announcements'
const BANNER_KEY = 'macros_dismissed_banner'
const WEIGH_IN_KEY = 'macros_dismissed_weigh_in'

export function seenAnnouncementIds(): string[] {
  const raw = readLocal(SEEN_KEY)
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
 * NOTE `readLocal` returns null both when the key is absent AND when localStorage
 * throws, which it does in Safari private mode. That browser therefore reads as
 * "first run" on every load: it sees the welcome each time and never the full
 * backlog. That is the safe direction to fail in, and it is deliberate. */
export function hasEverSeenAnnouncements(): boolean {
  return readLocal(SEEN_KEY) !== null
}

export function markAnnouncementsSeen(ids: string[]) {
  const merged = new Set([...seenAnnouncementIds(), ...ids])
  writeLocal(SEEN_KEY, JSON.stringify([...merged]))
}

// Keyed by the banner's own text: editing the notice in the hosting dashboard
// makes it a new notice, which should reappear even for someone who dismissed
// the last one.
export function isBannerDismissed(banner: string): boolean {
  return readLocal(BANNER_KEY) === banner
}

export function dismissBanner(banner: string) {
  writeLocal(BANNER_KEY, banner)
}

// Keyed by the date it was dismissed for, exactly as the banner above is keyed
// by its own text. That is what makes "once a day" need no new storage concept
// and no cleanup: tomorrow's date does not match the stored one, so yesterday's
// dismissal expires by itself. A set of dismissed dates would grow forever and
// would still need this comparison.
export function isWeighInNudgeDismissed(isoDate: string): boolean {
  return readLocal(WEIGH_IN_KEY) === isoDate
}

export function dismissWeighInNudge(isoDate: string) {
  writeLocal(WEIGH_IN_KEY, isoDate)
}
