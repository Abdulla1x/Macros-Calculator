import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import StatusBanner from '../components/StatusBanner'
import WarmupNotice from '../components/WarmupNotice'
import { useAnnouncements } from '../hooks/useAnnouncements'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { logout } = useAuth()
  // Captured once, on the first render, because the effect below then removes
  // it from the URL. Reading it in an initialiser rather than an effect is what
  // makes that safe under StrictMode, which mounts every component twice in
  // dev — an effect-based read would find the query string already stripped on
  // the second pass.
  const [token] = useState(() => searchParams.get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const announcements = useAnnouncements()

  useEffect(() => {
    // Take the token out of the address bar and the back-history entry. The
    // Referrer-Policy in vercel.json already stops it leaking to other origins,
    // but it would otherwise sit in browser history and in the host's request
    // logs for as long as those are kept.
    if (searchParams.has('token')) {
      navigate('/reset-password', { replace: true })
    }
  }, [searchParams, navigate])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await api.resetPassword(token, password)
      // Any session stored on THIS device is now revoked server-side — the
      // reset moved password_changed_at past its token. Clearing it locally
      // keeps AuthContext from holding a user it can no longer authenticate.
      logout()
      navigate('/login', {
        replace: true,
        state: { notice: 'Password updated — log in with your new password.' },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
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
        {token ? (
          <Card as="form" pad="lg" className="space-y-4" onSubmit={handleSubmit}>
            <h2 className="text-lg font-semibold">Choose a new password</h2>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-400">New password</span>
              <TextInput size="md" className="w-full"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <span className="mt-1 block text-xs text-ink-faint">
                At least 8 characters.
              </span>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-400">Confirm password</span>
              <TextInput size="md" className="w-full"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
            {error && <p className="text-sm text-rose-400">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {submitting ? 'Saving…' : 'Set new password'}
            </button>
          </Card>
        ) : (
          <Card pad="lg" className="space-y-3 text-sm">
            <h2 className="text-lg font-semibold">That link is incomplete</h2>
            <p className="text-slate-400">
              This page needs the link from your reset email. Some mail apps cut
              long links in half — try copying the whole thing, or request a new
              one.
            </p>
            <p className="text-center">
              <Link
                to="/forgot-password"
                className="text-emerald-400 hover:text-emerald-300"
              >
                Request a new link
              </Link>
            </p>
          </Card>
        )}
        <WarmupNotice />
      </div>
    </div>
  )
}
