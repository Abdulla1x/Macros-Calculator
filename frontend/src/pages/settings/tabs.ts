// The Settings addresses, in bar order.
//
// One array drives three things that used to have no single source of truth
// once the page was split: the tab bar, the <h1> each panel renders, and the
// redirect /settings falls back to. Adding a section means adding a row here
// and a <Route> in App.tsx, and nothing else.

export interface SettingsTab {
  /** The path segment under /settings/. */
  path: string
  /** Tab bar label. Short on purpose -- four of these share a 360px row. */
  label: string
  /** The page <h1>.
   *
   * Phase 15's rule is one distinctly-named <h1> per route, so heading
   * navigation can tell pages apart. Five sub-routes all titled "Settings"
   * would quietly undo that, which is why the word "Settings" is an eyebrow
   * above the heading rather than the heading itself. */
  title: string
  /** Account is deliberately off the bar, the same posture /admin has in the
   *  main nav: somewhere you go when you mean to, not a fifth thing to choose
   *  between. It also keeps Danger zone off a control you can hit by accident
   *  while reaching for the tab beside it. */
  inBar: boolean
}

const GOALS: SettingsTab = {
  path: 'goals',
  label: 'Goals',
  title: 'Goals & targets',
  inBar: true,
}

export const SETTINGS_TABS: SettingsTab[] = [
  GOALS,
  { path: 'body', label: 'Body', title: 'Body profile', inBar: true },
  { path: 'trackers', label: 'Trackers', title: 'Daily trackers', inBar: true },
  { path: 'food', label: 'Library', title: 'Your library', inBar: true },
  { path: 'account', label: 'Account', title: 'Account & data', inBar: false },
]

/** The tab a pathname is on, falling back to Goals.
 *
 * Returns a tab rather than `undefined` so the layout always has a heading:
 * an unmatched segment renders NotFound at the router level and never reaches
 * here, so the fallback is for the redirect's brief pass through /settings.
 */
export function settingsTabFor(pathname: string): SettingsTab {
  const segment = pathname.split('/')[2] ?? ''
  return SETTINGS_TABS.find((tab) => tab.path === segment) ?? GOALS
}
