import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { isSessionPersistent } from '../auth/token'
import StatusBanner from '../components/StatusBanner'
import WarmupNotice from '../components/WarmupNotice'
import { useAnnouncements } from '../hooks/useAnnouncements'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'
import Field from '../components/ui/Field'
import Button from '../components/ui/Button'
import { useLiveMessage } from '../hooks/useLiveMessage'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  useLiveMessage(error)
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
        <Card as="form" pad="lg" className="space-y-4" onSubmit={handleSubmit}>
          <h2 className="text-lg font-semibold">Log in</h2>
          {!persistentSession && (
            <p className="text-sm text-amber-400">
              This browser is blocking site data, so you&rsquo;ll stay signed in
              only until you close this tab. Allowing it for this site, or
              leaving private browsing, keeps you signed in.
            </p>
          )}
          {notice && <p className="text-sm text-emerald-400">{notice}</p>}
          <Field label="Email">
            <TextInput size="md"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Password">
            <TextInput size="md"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full"
            />
          </Field>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <Button
            type="submit"
            disabled={submitting}
            className="w-full px-5 py-2"
          >
            {submitting ? 'Logging in…' : 'Log in'}
          </Button>
          {/* `underline` is not decoration, and the rule is PROSE, not sentences.
              A link inside a sentence may not be distinguished by colour alone
              (WCAG 1.4.1) unless it clears 3:1 against the surrounding text --
              emerald-400 on slate-400 measures 1.35. That is what the audit
              flagged, at four links.

              The other two -- this one and "Back to log in" -- are each the only
              thing in their paragraph, so strictly they are not in a text block
              and the rule does not reach them. They are underlined anyway: they
              are prose text sitting inches from links that now are, and a user
              who has just learnt that underline means link should not meet one
              that does not. Link-SHAPED CONTROLS are the ones left alone -- nav
              items, card links, anything wearing a button -- because those are
              not prose and never read as a sentence. */}
          <p className="text-center text-sm text-slate-400">
            <Link
              to="/forgot-password"
              className="text-emerald-400 underline hover:text-emerald-300"
            >
              Forgot your password?
            </Link>
          </p>
          <p className="text-center text-sm text-slate-400">
            No account?{' '}
            <Link to="/signup" className="text-emerald-400 underline hover:text-emerald-300">
              Sign up
            </Link>
          </p>
        </Card>
        <WarmupNotice />
      </div>
    </div>
  )
}
