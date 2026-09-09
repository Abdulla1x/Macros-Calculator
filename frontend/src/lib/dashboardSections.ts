// Which dashboard sections this device keeps folded away.
//
// Both shortcut cards -- Saved meals and Recently logged -- are navigation
// rather than information. Twelve tappable cells sat between the rings and the
// meal list, and because the tracker grid is `sm:grid-cols-2` it stacks into
// three full-width cards below 640px: on a 390px phone that put today's meals
// roughly five screens down. They are collapsed by default because the thing
// you came to read is underneath them, while the thing they offer is a
// shortcut for something the header's "+ Log a meal" already does.
//
// Per device rather than per account, for the reason lib/dismissals.ts gives:
// a UI preference, not user data, so no table, no column and no request.
//
// NOT keyed by account id, unlike lib/recentTemplates.ts. That key exists
// because template ids are small integers assigned per user, so one account's
// id would silently address another's. A section name collides with nothing,
// and someone who folds a card away means it for the device in their hand.

import { readLocal, writeLocal } from './storage'

const KEY = 'macros_dashboard_sections'

export type DashboardSection = 'savedMeals' | 'recentlyLogged'

/** The sections this device has opened. Storing the EXPANDED ones rather than a
 *  map of booleans is what makes "collapsed" the default for free: absence and
 *  a fresh device are the same state, and neither needs a written record.
 *
 *  It also decides how this fails. `readLocal` returns null both when the key
 *  is absent and when localStorage throws -- Safari's private mode, or a
 *  browser set to block site data -- so those browsers read as "everything
 *  collapsed" on every load. That is the safe direction: a folded card is one
 *  tap from open, where a wrongly expanded one is the bug this file exists to
 *  fix. Same trade lib/dismissals.ts documents for its own key. */
function expanded(): string[] {
  const raw = readLocal(KEY)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((name) => typeof name === 'string') : []
  } catch {
    return []
  }
}

export function isSectionExpanded(section: DashboardSection): boolean {
  return expanded().includes(section)
}

export function setSectionExpanded(section: DashboardSection, open: boolean) {
  const rest = expanded().filter((name) => name !== section)
  writeLocal(KEY, JSON.stringify(open ? [...rest, section] : rest))
}
