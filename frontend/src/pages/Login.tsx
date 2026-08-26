import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { isSessionPersistent } from '../auth/token'
import StatusBanner from '../components/StatusBanner'
import WarmupNotice from '../components/WarmupNotice'
import { useAnnouncements } from '../hooks/useAnnouncements'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Probed once per mount: the answer cannot change while the page is open.
  const [persistentSession] = useState(isSessionPersistent)
  const [submitting, setSubmitting] = useState(false)
  // An outage notice matters most here: this is where someone lands when the
  // app looks broken to them.
  const announcements = useAnnouncements()
  // Set by the reset page, which sends people here rather than logging them in.
  const notice = (location.state as { notice?: string } | null)?.notice ?? null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate((location.state as { from?: string } | null)?.from ?? '/', {
        replace: true,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="text-3xl">🍽️</span>
          <h1 className="text-xl font-bold tracking-tight">Macros Calculator</h1>
        </div>
        <StatusBanner banner={announcements?.banner ?? null} />
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6"
        >
          <h2 className="text-lg font-semibold">Log in</h2>
          {!persistentSession && (
            <p className="text-sm text-amber-400">
              This browser is blocking site data, so you&rsquo;ll stay signed in
              only until you close this tab. Allowing it for this site, or
              leaving private browsing, keeps you signed in.
            </p>
          )}
          {notice && <p className="text-sm text-emerald-400">{notice}</p>}
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-500"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-500"
            />
          </label>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {submitting ? 'Logging in…' : 'Log in'}
          </button>
          <p className="text-center text-sm text-slate-400">
            <Link
              to="/forgot-password"
              className="text-emerald-400 hover:text-emerald-300"
            >
              Forgot your password?
            </Link>
          </p>
          <p className="text-center text-sm text-slate-400">
            No account?{' '}
            <Link to="/signup" className="text-emerald-400 hover:text-emerald-300">
              Sign up
            </Link>
          </p>
        </form>
        <WarmupNotice />
      </div>
    </div>
  )
}
