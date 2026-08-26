import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import StatusBanner from '../components/StatusBanner'
import WarmupNotice from '../components/WarmupNotice'
import { useAnnouncements } from '../hooks/useAnnouncements'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const announcements = useAnnouncements()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.forgotPassword(email)
      setSent(true)
    } catch (err) {
      // Only real failures land here — a 503 when email isn't configured, a 429,
      // or the network. An address with no account still answers 200, by design.
      setError(err instanceof Error ? err.message : 'Request failed')
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
        {sent ? (
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm">
            <h2 className="text-lg font-semibold">Check your inbox</h2>
            <p className="text-slate-400">
              If an account exists for <span className="text-slate-200">{email}</span>,
              a reset link is on its way. It works for one hour and can only be
              used once.
            </p>
            {/* Written here rather than echoed from the API: this is a fact
                about how the mail is delivered, not about the request. Our
                sending address is rewritten by the email provider because we
                don't own a domain yet, so the message genuinely looks like it
                came from a stranger — saying so up front is the difference
                between "check spam" and "report phishing". */}
            <p className="text-ink-faint">
              It arrives from <span className="text-slate-300">Macros Calculator</span>{' '}
              but at an unfamiliar <code className="text-slate-300">brevosend.com</code>{' '}
              address, so check your spam folder if it isn't there in a few
              minutes.
            </p>
            <p className="text-center text-slate-400">
              <Link to="/login" className="text-emerald-400 hover:text-emerald-300">
                Back to log in
              </Link>
            </p>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <h2 className="text-lg font-semibold">Reset your password</h2>
            <p className="text-sm text-slate-400">
              Enter your email and we'll send you a link to choose a new
              password.
            </p>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-400">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-500 focus:outline-none"
              />
            </label>
            {error && <p className="text-sm text-rose-400">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {submitting ? 'Sending…' : 'Send reset link'}
            </button>
            <p className="text-center text-sm text-slate-400">
              Remembered it?{' '}
              <Link to="/login" className="text-emerald-400 hover:text-emerald-300">
                Log in
              </Link>
            </p>
          </form>
        )}
        <WarmupNotice />
      </div>
    </div>
  )
}
