// Which saved meals this device logged most recently, so Quick log's first row
// is the ones actually being used rather than the ones most recently created.
//
// Client-side on purpose. Doing it server-side means a `last_used_at` column,
// and routers/meal_templates.py already documents why that is a cross-dialect
// trap: Postgres sorts NULLs first under DESC and SQLite sorts them last, so
// every never-used template would float to the top in production while the
// SQLite suite showed it working. This gets most of the value for no schema,
// no migration and no request, and degrades to plain server order on a new
// device -- which is exactly today's behaviour.
//
// Same reasoning lib/dismissals.ts gives for living in localStorage: a UI
// preference, not user data.

import { readLocal, writeLocal } from './storage'

/** How many ids to remember. Twice the six Quick log shows, so the visible row
 *  keeps settling as habits change instead of being pinned by one busy week,
 *  without the list growing without bound. */
const REMEMBERED = 12

/** Keyed by account id. localStorage is per-device and shared by every account
 *  signed in on it, and template ids are small integers assigned per user -- so
 *  an unkeyed list would let one account float a template in another's Quick log
 *  purely because the two ids collided. */
const keyFor = (userId: number) => `macros_recent_templates:${userId}`

export function recentTemplateIds(userId: number): number[] {
  const raw = readLocal(keyFor(userId))
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'number') : []
  } catch {
    return []
  }
}

export function rememberTemplate(userId: number, id: number) {
  const next = [id, ...recentTemplateIds(userId).filter((seen) => seen !== id)]
  writeLocal(keyFor(userId), JSON.stringify(next.slice(0, REMEMBERED)))
}

/** Most recently tapped first, then everything else in the order the server
 *  gave, which is newest first.
 *
 * Ids that no longer match a template are ignored rather than pruned: the list
 * is at most twelve entries, and rewriting storage from a render path to tidy
 * it would be a write nobody asked for.
 *
 * The unranked sentinel is `recent.length`, NOT Infinity. Two unranked items
 * would compare Infinity - Infinity = NaN, and a comparator returning NaN has
 * undefined behaviour -- it would scramble the server's ordering for every
 * template that had never been tapped. A finite sentinel makes their difference
 * 0, which a stable sort leaves alone.
 */
export function byRecentUse<T extends { id: number }>(items: T[], userId: number): T[] {
  const recent = recentTemplateIds(userId)
  if (recent.length === 0) return items
  const rank = new Map(recent.map((id, index) => [id, index]))
  const rankOf = (id: number) => rank.get(id) ?? recent.length
  return [...items].sort((a, b) => rankOf(a.id) - rankOf(b.id))
}
