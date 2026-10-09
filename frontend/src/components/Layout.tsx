import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAnnouncements } from '../hooks/useAnnouncements'
import { useSettings } from '../settings/SettingsContext'
import AnnouncementsModal from './AnnouncementsModal'
import StatusBanner from './StatusBanner'
import WeighInNudge from './WeighInNudge'
import WakingNotice from './WakingNotice'
import { RailNav, TabBar } from './shell/AppNav'
import ProgressSubnav from './shell/ProgressSubnav'
import { sectionFor } from './shell/sections'
import Wordmark from './shell/Wordmark'

// A warm server answers settings in well under a second, so this never fires in
// normal use. Past it, the instance is almost certainly spinning up — and a
// blank page with no explanation is what makes a returning user assume the app
// broke rather than that it is waking. Same idea as RETRY_NOTICE_AFTER_MS in
// MealAnalyzer: say nothing until the wait stops looking normal.
const COLD_START_NOTICE_AFTER_MS = 3_000

export default function Layout() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const section = sectionFor(pathname)
  // /admin is the one route in this app that is genuinely desktop-only — a
  // twelve-column table of per-account counts, read by one person on a big
  // screen. Every other page is designed phone-first and 5xl is right for it,
  // but at that width the admin table was crammed into ~640px in the middle of
  // a 2000px display and had to scroll sideways to be read at all. This is the
  // one place the extra width is clearly correct rather than a preference, and
  // it is what makes the tracker columns affordable as words instead of bare
  // emoji.
  const wide = pathname === '/admin'
  // One fetch feeds both the banner and the modal.
  const announcements = useAnnouncements()
  // The shared settings fetch doubles as the cold-start probe: it is the first
  // authenticated request of the session, so if it is slow, everything is.
  const { loading: settingsLoading } = useSettings()
  const [coldStart, setColdStart] = useState(false)
  // When the wait actually began, which is not when the notice appears. The
  // notice is held back COLD_START_NOTICE_AFTER_MS, so a progress bar started
  // at its mount would run three seconds behind the fetch it describes — and
  // three seconds is most of the difference between the two measured boot
  // clusters. Passed to WakingNotice below.
  const waitStartedAt = useRef(Date.now())

  useEffect(() => {
    if (!settingsLoading) {
      setColdStart(false)
      return
    }
    waitStartedAt.current = Date.now()
    const timer = setTimeout(() => setColdStart(true), COLD_START_NOTICE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [settingsLoading])

  return (
    <div className="min-h-screen bg-ground desk:flex">
      {/* First thing in the tab order. Without it a keyboard user tabs through
          the nav on every single page before reaching content. Uses :focus
          rather than :focus-visible on purpose -- the link is only ever
          reachable by keyboard, and :focus is the pattern with the widest
          support for this one case. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-action focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-action-ink"
      >
        Skip to content
      </a>

      {/* Desktop: the side rail (DESIGN.md, Layout). Sticky, so the nav stays
          reachable from the bottom of a long page. Phones get TabBar below
          instead; there is no top header at any width any more -- each page
          owns its title, and Log out lives in Settings -> Account (UA-8). */}
      <aside className="sticky top-0 hidden h-screen w-[236px] shrink-0 flex-col gap-[18px] border-r border-rule px-4 py-[22px] desk:flex">
        {/* self-start so the gauge spans the name, as DESIGN.md's mark draws it,
            instead of stretching to the rail's width. */}
        <Wordmark className="mb-1.5 self-start" />
        <RailNav active={section} />
        {/* Who is signed in, where the old header said it. Truncated, with the
            full address on hover; Settings -> Account states it in full. */}
        <p className="mt-auto truncate text-small text-ink-2" title={user?.email}>
          {user?.email}
        </p>
      </aside>

      {/* The bottom padding clears the fixed tab bar and its safe-area inset
          (--shell-bottom, index.css), so the last thing on a page is never
          trapped underneath it; the top one clears a notch. */}
      <main
        id="main"
        tabIndex={-1}
        className="min-w-0 flex-1 px-4 pt-[calc(env(safe-area-inset-top)+1.5rem)] pb-[calc(var(--shell-bottom)+1.5rem)] desk:px-8 desk:py-8"
      >
        <div className={`mx-auto ${wide ? 'max-w-7xl' : 'max-w-5xl'}`}>
          <StatusBanner banner={announcements?.banner ?? null} />
          {/* Below the status banner on purpose: an outage notice outranks a
              reminder. Above the outlet so it reaches someone who never
              navigates to /weight, which is the whole point of it. Renders
              nothing at all unless the reminder has been switched on. */}
          <WeighInNudge />
          {coldStart && (
            <WakingNotice
              startedAt={waitStartedAt.current}
              className="mb-4 rounded-control bg-surface px-3 py-2 text-center text-xs text-ink-muted"
            />
          )}
          {section === 'progress' && <ProgressSubnav pathname={pathname} />}
          {/* A 150ms fade when the page changes (DESIGN.md: tab changes are a
              crossfade). Keyed by the first path segment, NOT the whole path:
              moving between Settings tabs must keep the Settings shell, and
              its unsaved draft, mounted. Plain CSS rather than Motion, so the
              first screen never waits on Motion's features to download. */}
          <div key={pathname.split('/')[1] ?? ''} className="animate-route-in">
            <Outlet />
          </div>
        </div>
      </main>

      <TabBar active={section} />
      <AnnouncementsModal items={announcements?.items ?? []} />
    </div>
  )
}
