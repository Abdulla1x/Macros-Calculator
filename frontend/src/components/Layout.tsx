import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAnnouncements } from '../hooks/useAnnouncements'
import { useSettings } from '../settings/SettingsContext'
import AnnouncementsModal from './AnnouncementsModal'
import StatusBanner from './StatusBanner'
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
      <aside className="border-b border-slate-800 bg-slate-900/60 md:flex md:min-h-screen md:w-60 md:flex-col md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="text-2xl">🍽️</span>
          <div>
            <h1 className="text-base font-bold tracking-tight">Macros Calculator</h1>
            <p className="text-xs text-ink-faint">Nutrition tracker</p>
          </div>
        </div>
        <nav className="flex gap-1 px-3 pb-3 md:flex-col md:pb-0">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`
              }
            >
              <span>{link.icon}</span>
              <span className="hidden sm:inline">{link.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center justify-between gap-2 border-t border-slate-800 px-5 py-3 md:mt-auto">
          <span className="truncate text-xs text-ink-faint" title={user?.email}>
            {user?.email}
          </span>
          <button
            onClick={logout}
            className="shrink-0 text-xs text-slate-400 hover:text-emerald-300"
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-5xl">
          <StatusBanner banner={announcements?.banner ?? null} />
          {coldStart && (
            <WakingNotice className="mb-4 rounded-lg bg-slate-900 px-3 py-2 text-center text-xs text-slate-400" />
          )}
          <Outlet />
        </div>
      </main>
      <AnnouncementsModal items={announcements?.items ?? []} />
    </div>
  )
}
