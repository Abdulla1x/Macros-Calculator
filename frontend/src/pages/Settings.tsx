import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import AlertDialog from '../components/AlertDialog'
import { validateSettingsField } from '../lib/limits'
import { useSettings } from '../settings/SettingsContext'
import type { Settings as SettingsType } from '../types'
import type { SettingsPanel } from './settings/panelContext'
import { SETTINGS_TABS, settingsTabFor } from './settings/tabs'

/** The Settings shell: one draft, one Save, five addresses.
 *
 * This page used to be a single scroll of twelve sections with the Save button
 * stranded in the middle of it -- three immediate-write sections and the whole
 * Account block rendered *below* the button that saves the ones above. The
 * concrete failure that fell out of that shape: edit your body profile, scroll
 * past Save to add a supplement, navigate away, and the profile edit is gone
 * with nothing having said so.
 *
 * Routes rather than an accordion or useState tabs, for a reason from the code
 * rather than from taste: the dashboard deep-links into the calorie planner, and
 * an accordion would open that link collapsed while tab state would break
 * back/forward. Every section now has an address.
 *
 * The draft lives here, above the router outlet, so switching tabs cannot lose
 * an unsaved edit -- only leaving /settings can.
 */
export default function Settings() {
  const { settings: saved, error: loadError, updateSettings } = useSettings()
  // A local working copy, so edits are not published to the rest of the app
  // until Save. Editing the shared object directly would make the dashboard
  // rings follow every keystroke in the goal fields, including half-typed
  // numbers on the way to the real one.
  const [draft, setDraft] = useState<SettingsType | null>(null)
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState('')
  // Bumped after every successful save, so the targets card refetches. The
  // numbers it shows are derived from the row that was just written, and a
  // stale card beside a fresh form is how you end up trusting the wrong one.
  const [targetsKey, setTargetsKey] = useState(0)
  // The refusal message for a value that has just been rejected and undone.
  const [rejected, setRejected] = useState<string | null>(null)
  const tab = settingsTabFor(useLocation().pathname)

  useEffect(() => {
    if (saved) setDraft(saved)
  }, [saved])

  if (!draft) {
    return <p className="text-slate-400">{loadError || 'Loading…'}</p>
  }
  const settings = draft

  const update = (patch: Partial<SettingsType>) => {
    setDraft({ ...settings, ...patch })
    setStatus('idle')
  }

  /** Refuse an out-of-range value the moment the user leaves the field.
   *
   * On blur rather than on change: validating every keystroke would reject
   * "7" on the way to typing "0.7". On blur the user has finished, and the
   * answer arrives while they are still looking at the field they typed it
   * into — not several fields later, attached to a failed Save.
   *
   * The value is *undone*, not merely flagged. Leaving a number the server is
   * certain to refuse sitting in the box looks accepted, and it would fail
   * again on the next save for a reason the user has by then forgotten. */
  const guard = (field: keyof SettingsType) => () => {
    const problem = validateSettingsField(field, settings[field] as number | null)
    if (!problem) return
    setRejected(problem)
    update({ [field]: saved ? saved[field] : null })
  }

  const save = async () => {
    setStatus('saving')
    try {
      // Through the context, so the dashboard rings and the Weight page's unit
      // pick up the change immediately instead of on their next remount.
      setDraft(await updateSettings(settings))
      setTargetsKey((key) => key + 1)
      setStatus('saved')
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  const context: SettingsPanel = {
    settings,
    update,
    guard,
    onRejected: setRejected,
    targetsKey,
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div>
          {/* "Settings" is the eyebrow, not the heading. Each panel owns the
              <h1>, so heading navigation lands on five distinct names instead
              of the same word five times. */}
          <p className="text-xs font-semibold tracking-wide text-ink-faint uppercase">
            Settings
          </p>
          <h1 className="text-2xl font-bold">{tab.title}</h1>
        </div>
        {/* Off the tab bar on purpose -- see the inBar note in tabs.ts. A link
            keeps it one tap away without putting account deletion next to the
            tab you were reaching for. */}
        <NavLink
          to="/settings/account"
          className={({ isActive }) =>
            `text-sm ${isActive ? 'text-emerald-300' : 'text-ink-faint hover:text-slate-300'}`
          }
        >
          Account &amp; data →
        </NavLink>
      </header>

      <nav
        aria-label="Settings sections"
        className="grid grid-cols-4 gap-1 rounded-card border border-line bg-surface p-1"
      >
        {SETTINGS_TABS.filter((item) => item.inBar).map((item) => (
          <NavLink
            key={item.path}
            to={`/settings/${item.path}`}
            className={({ isActive }) =>
              `rounded-control px-2 py-2 text-center text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'text-ink-muted hover:bg-raised hover:text-ink'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Outlet context={context} />

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={status === 'saving'}
          className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {status === 'saving' ? 'Saving…' : 'Save settings'}
        </button>
        {status === 'saved' && <span className="text-sm text-emerald-400">Saved ✓</span>}
        {status === 'error' && <span className="text-sm text-rose-400">{error}</span>}
      </div>

      {rejected && (
        <AlertDialog
          title="That value can't be used"
          message={rejected}
          onClose={() => setRejected(null)}
        />
      )}
    </div>
  )
}
