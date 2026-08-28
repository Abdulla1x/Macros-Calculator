import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAnnouncements } from '../hooks/useAnnouncements'
import { useSettings } from '../settings/SettingsContext'
import AnnouncementsModal from './AnnouncementsModal'
import StatusBanner from './StatusBanner'
import WeighInNudge from './WeighInNudge'
import WakingNotice from './WakingNotice'

// A warm server answers settings in well under a second, so this never fires in
// normal use. Past it, the instance is almost certainly spinning up — and a
// blank page with no explanation is what makes a returning user assume the app
// broke rather than that it is waking. Same idea as RETRY_NOTICE_AFTER_MS in
// MealAnalyzer: say nothing until the wait stops looking normal.
const COLD_START_NOTICE_AFTER_MS = 3_000

const links = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/log', label: 'Log Meal', icon: '🍽️' },
  { to: '/weight', label: 'Weight', icon: '⚖️' },
  { to: '/analytics', label: 'Analytics', icon: '📈' },
  { to: '/review', label: 'Review', icon: '🗓️' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  // One fetch feeds both the banner and the modal.
  const announcements = useAnnouncements()
  // The shared settings fetch doubles as the cold-start probe: it is the first
  // authenticated request of the session, so if it is slow, everything is.
  const { loading: settingsLoading } = useSettings()
  const [coldStart, setColdStart] = useState(false)

  useEffect(() => {
    if (!settingsLoading) {
      setColdStart(false)
      return
    }
    const timer = setTimeout(() => setColdStart(true), COLD_START_NOTICE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [settingsLoading])

  return (
    <div className="min-h-screen md:flex">
      {/* First thing in the tab order. Without it a keyboard user tabs through
          five nav items on every single page before reaching content. Uses
          :focus rather than :focus-visible on purpose -- the link is only ever
          reachable by keyboard, and :focus is the pattern with the widest
          support for this one case. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-ink"
      >
        Skip to content
      </a>
      {/* One element serves both shells. Below md it is a single sticky top bar
          holding brand and account — it used to be three stacked rows, ~170px of
          chrome before any content on a phone. At md+ it is the 240px rail it
          always was, now sticky too, so nav is reachable from the bottom of a
          long Settings page at every width. bg-surface is opaque on purpose:
          theme-color in index.html is the same #0f172a, so the PWA status bar
          meets the header with no seam. */}
      <aside className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 md:h-screen md:w-60 md:flex-col md:items-stretch md:justify-start md:gap-0 md:self-start md:border-r md:border-b-0 md:px-0 md:py-0">
        <div className="flex min-w-0 items-center gap-2 md:px-5 md:py-5">
          <span className="text-2xl" aria-hidden="true">
            🍽️
          </span>
          <div className="min-w-0">
            {/* Not an <h1>: it is the site identity, repeated on every page. Each
                page now owns the single <h1>, so heading navigation can tell them
                apart instead of landing on "Macros Calculator" five times. */}
            <span className="block truncate text-base font-bold tracking-tight">Macros Calculator</span>
            <p className="hidden text-xs text-ink-faint md:block">Nutrition tracker</p>
          </div>
        </div>

        {/* Below md this leaves the aside entirely and becomes a fixed bottom tab
            bar — the convention in every app this was measured against, and the
            single biggest "feels like a real app" change. It is out of flow, so
            the aside's justify-between sees only brand and account.

            The labels are now always rendered. They used to be `hidden sm:inline`,
            and `hidden` is display:none, which removes them from the accessibility
            tree — so every phone got five unlabelled emoji as the only accessible
            name (audit item 4). Showing them beats sr-only: it helps everyone, and
            a five-column bar has the room at 360px.

            pb-[env(safe-area-inset-bottom)] is not optional. index.html carries
            the matching viewport-fit=cover; without the pair, the row sits under
            the home indicator on a curved display. */}
        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:static md:flex md:flex-col md:gap-1 md:border-t-0 md:bg-transparent md:px-3 md:pb-0"
        >
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) =>
                `flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors min-[360px]:text-[11px] md:min-h-0 md:flex-row md:justify-start md:gap-3 md:rounded-control md:px-3 md:py-2 md:text-sm ${
                  isActive
                    ? 'text-emerald-300 md:bg-emerald-500/15'
                    : 'text-ink-muted hover:text-ink md:hover:bg-raised'
                }`
              }
            >
              {/* Decorative now that the label is always present. It used to BE
                  the accessible name. */}
              <span className="text-lg leading-none md:text-base" aria-hidden="true">
                {link.icon}
              </span>
              <span>{link.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="flex min-w-0 items-center gap-3 md:mt-auto md:justify-between md:border-t md:border-line md:px-5 md:py-3">
          {/* Hidden below sm so the brand is not squeezed to "Macros ..." on a
              360px phone. Safe to hide rather than sr-only: it is redundant
              information, not a control's only accessible name, and Settings ->
              Account states "Signed in as ..." on every width. */}
          <span className="hidden min-w-0 truncate text-xs text-ink-faint sm:block" title={user?.email}>
            {user?.email}
          </span>
          <button onClick={logout} className="shrink-0 text-xs text-ink-muted hover:text-emerald-300">
            Log out
          </button>
        </div>
      </aside>
      {/* The bottom padding clears the fixed tab bar and its safe-area inset, so
          the last card on a page is never trapped underneath it. */}
      <main id="main" tabIndex={-1} className="flex-1 px-4 py-6 pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:px-8 md:py-8 md:pb-8">
        <div className="mx-auto max-w-5xl">
          <StatusBanner banner={announcements?.banner ?? null} />
          {/* Below the status banner on purpose: an outage notice outranks a
              reminder. Above the outlet so it reaches someone who never
              navigates to /weight, which is the whole point of it. Renders
              nothing at all unless the reminder has been switched on. */}
          <WeighInNudge />
          {coldStart && (
            <WakingNotice className="mb-4 rounded-control bg-surface px-3 py-2 text-center text-xs text-ink-muted" />
          )}
          <Outlet />
        </div>
      </main>
      <AnnouncementsModal items={announcements?.items ?? []} />
    </div>
  )
}
