/** The new navigation's four places (overhaul 0a, Option A), and which of
 *  today's routes belongs to each.
 *
 *  Until the redesigned screens exist (phase 2), the tabs lead to the pages
 *  the app already has: Progress opens Analytics, and Weight and the weekly
 *  review count as Progress, reached by a sub-nav at the top of all three.
 *  When phase 2 merges them into one Progress screen, this map shrinks; it is
 *  the one place that knows. */
export type Section = 'today' | 'progress' | 'log' | 'you'

export const SECTION_HOME: Record<Section, string> = {
  today: '/',
  progress: '/analytics',
  log: '/log',
  you: '/settings',
}

/** The pages under Progress, in sub-nav order. */
export const PROGRESS_PAGES = [
  { to: '/analytics', label: 'Nutrition' },
  { to: '/weight', label: 'Weight' },
  { to: '/review', label: 'Weekly review' },
] as const

const under = (pathname: string, base: string) => pathname === base || pathname.startsWith(`${base}/`)

/** Which tab is current for a path, or null for a page that belongs to none
 *  (Admin, an unknown address). */
export function sectionFor(pathname: string): Section | null {
  if (pathname === '/') return 'today'
  if (PROGRESS_PAGES.some((page) => under(pathname, page.to))) return 'progress'
  if (under(pathname, '/log')) return 'log'
  if (under(pathname, '/settings') || under(pathname, '/whats-new')) return 'you'
  return null
}
