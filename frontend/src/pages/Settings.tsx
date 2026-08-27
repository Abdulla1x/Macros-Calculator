import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import AlertDialog from '../components/AlertDialog'
import { validateSettingsField } from '../lib/limits'
import { useSettings } from '../settings/SettingsContext'
import type { Settings as SettingsType } from '../types'
import type { SettingsPanel } from './settings/panelContext'
import { SETTINGS_TABS, settingsTabFor } from './settings/tabs'
import Button from '../components/ui/Button'

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
/** Does the working copy differ from the row the server has?
 *
 * Deliberately not `JSON.stringify(a) !== JSON.stringify(b)`. That is correct
 * only while key order stays stable, which it does today purely because the
 * draft is always built by spreading the saved row -- a rule that holds by
 * luck, and this codebase has been bitten before by a comment asserting an
 * invariant its own contents did not enforce. Walking the keys costs nothing
 * and needs no such assumption. `water_quick_adds` is the only array on the
 * row, hence the element-wise arm.
 */
function settingsDiffer(a: SettingsType, b: SettingsType): boolean {
  return (Object.keys(a) as (keyof SettingsType)[]).some((key) => {
    const left = a[key]
    const right = b[key]
    if (Array.isArray(left) && Array.isArray(right)) {
      return (
        left.length !== right.length ||
        left.some((value, index) => value !== right[index])
      )
    }
    return left !== right
  })
}

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

  // Computed before the early return below, because the two effects that
  // depend on it are hooks and cannot sit after a conditional return.
  const dirty = draft !== null && saved !== null && settingsDiffer(draft, saved)

  // Covers a reload, a closed tab and a followed external link. It does NOT
  // cover in-app navigation: react-router 7's useBlocker needs a data router
  // and this app mounts <BrowserRouter> + <Routes>, so leaving /settings by
  // the nav still drops an unsaved draft silently. What the sticky bar buys is
  // that the draft can no longer be forgotten about -- it cannot scroll away
  // and it does not hide behind a tab switch, which is where the loss actually
  // came from.
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // "Saved ✓" is an acknowledgement, not a state to sit in. Without this the
  // bar would stay on screen after every save until the next keystroke, which
  // is a permanent strip of chrome reporting something that already happened.
  useEffect(() => {
    if (status !== 'saved') return
    const timer = setTimeout(() => setStatus('idle'), 2_500)
    return () => clearTimeout(timer)
  }, [status])

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

      {/* Pinned to the bottom of the viewport rather than sitting at the end of
          the page, which is the whole fix: the old button was ten sections down
          with more sections below it, so the way to lose an edit was simply to
          scroll past it.

          It appears for any unsaved change to the settings row, on whichever of
          the three deferred tabs you are standing -- NOT only for the tab that
          made the change. Per-tab visibility would hide a pending Body edit the
          moment you clicked Trackers, which is the same silent loss moved from
          scrolling to tab-switching. Ticking a supplement or correcting a food
          still summons nothing, because neither touches this row.

          bottom clears the fixed tab bar (min-h-[3.25rem] plus its safe-area
          inset in Layout.tsx); at md+ there is no bottom bar to clear. */}
      {tab.deferred && (dirty || status !== 'idle') && (
        <div className="sticky bottom-[calc(3.25rem+env(safe-area-inset-bottom))] z-20 md:bottom-4">
          <div className="flex items-center justify-between gap-3 rounded-card border border-line-strong bg-raised px-4 py-3 shadow-lg shadow-slate-950/50">
            <p className="min-w-0 text-sm">
              {status === 'saved' ? (
                <span className="text-emerald-400">Saved ✓</span>
              ) : status === 'error' ? (
                <span className="text-rose-400">{error}</span>
              ) : (
                <span className="text-ink-muted">You have unsaved changes</span>
              )}
            </p>
            {status !== 'saved' && (
              <Button
                onClick={save}
                disabled={status === 'saving'}
                className="shrink-0 px-5 py-2"
              >
                {status === 'saving' ? 'Saving…' : 'Save'}
              </Button>
            )}
          </div>
        </div>
      )}

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
