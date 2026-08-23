import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import AlertDialog from '../components/AlertDialog'
import {
  DEFAULT_WATER_QUICK_ADDS,
  MAX_WATER_GOAL_ML,
  MAX_WATER_QUICK_ADD_ML,
  MAX_STEPS_PER_DAY,
  MAX_WATER_QUICK_ADDS,
  MAX_SUPPLEMENTS,
  MAX_SUPPLEMENT_DOSE,
  MAX_SUPPLEMENT_NAME,
  MAX_SUPPLEMENT_TIMES,
  WATER_ML_PER_KG,
  validateSettingsField,
  validateSupplement,
  validateWaterQuickAdd,
} from '../lib/limits'
import { cmToFtIn, ftInToCm } from '../lib/units'
import { useSettings } from '../settings/SettingsContext'
import type {
  ActivityLevel,
  BodyTargets,
  ImportResult,
  Sex,
  Settings as SettingsType,
  Supplement,
} from '../types'

interface GoalField {
  key: 'calorie_goal' | 'protein_goal' | 'carbs_goal' | 'fat_goal'
  label: string
  unit: string
}

const goalFields: GoalField[] = [
  { key: 'calorie_goal', label: 'Daily calories', unit: 'kcal' },
  { key: 'protein_goal', label: 'Daily protein', unit: 'g' },
  { key: 'carbs_goal', label: 'Daily carbs', unit: 'g' },
  { key: 'fat_goal', label: 'Daily fat', unit: 'g' },
]

// Ported from LogMeal.tsx rather than using the bare Number() the goal fields
// use below. For a nullable profile field the difference matters: Number('')
// is 0, and a height of zero is a very different claim from "not set yet".
const num = (value: string) => {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const sexOptions: { value: Sex; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

const activityOptions: { value: ActivityLevel; label: string }[] = [
  { value: 'sedentary', label: 'Sedentary — desk job, little exercise' },
  { value: 'light', label: 'Light — exercise 1–3 days a week' },
  { value: 'moderate', label: 'Moderate — exercise 3–5 days a week' },
  { value: 'active', label: 'Active — hard exercise 6–7 days a week' },
  { value: 'very_active', label: 'Very active — physical job, or twice a day' },
]

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

  const showGoal = (key: GoalField['key']) =>
    key === 'carbs_goal' ? settings.track_carbs : key === 'fat_goal' ? settings.track_fat : true

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold">Settings</h2>
        <p className="text-sm text-slate-400">Choose what to track and set your daily goals.</p>
      </header>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-3 font-semibold">Tracked macros</h3>
        <p className="mb-4 text-sm text-slate-400">
          Calories and protein are always tracked. Enable carbs and fat if you want the full
          breakdown — they appear on the dashboard, meal log and analytics.
        </p>
        <div className="flex flex-wrap gap-4">
          {(
            [
              { key: 'track_carbs', label: 'Track carbs' },
              { key: 'track_fat', label: 'Track fat' },
            ] as const
          ).map(({ key, label }) => (
            <label
              key={key}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm"
            >
              <input
                type="checkbox"
                checked={settings[key]}
                onChange={(event) => update({ [key]: event.target.checked })}
                className="h-4 w-4 accent-emerald-500"
              />
              {label}
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-3 font-semibold">Units</h3>
        <p className="mb-4 text-sm text-slate-400">
          How weights are shown on the Weight page. Entries are stored the same way
          either way, so switching converts your history rather than rewriting it.
        </p>
        <div className="flex flex-wrap gap-4">
          {(
            [
              { value: 'kg', label: 'Kilograms (kg)' },
              { value: 'lb', label: 'Pounds (lb)' },
            ] as const
          ).map(({ value, label }) => (
            <label
              key={value}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm"
            >
              <input
                type="radio"
                name="weight_unit"
                value={value}
                checked={settings.weight_unit === value}
                onChange={() => update({ weight_unit: value })}
                className="h-4 w-4 accent-emerald-500"
              />
              {label}
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-1 font-semibold">Body profile</h3>
        <p className="mb-4 text-sm text-slate-400">
          Optional, and the app works fine without it. Fill it in and we can work
          out your BMI, roughly what you burn in a day, and daily targets that
          follow your weight instead of staying where you first set them.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <HeightField settings={settings} update={update} onBlur={guard('height_cm')} />

          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Date of birth</span>
            <input
              type="date"
              value={settings.birth_date ?? ''}
              onChange={(event) => update({ birth_date: event.target.value || null })}
              className={fieldClass}
              style={{ colorScheme: 'dark' }}
            />
            <span className="mt-1 block text-xs text-slate-500">
              Stored as the date, so your age stays right without you editing it.
            </span>
          </label>

          <label className="block text-sm sm:col-span-2">
            <span className="mb-1 block text-slate-400">Activity level</span>
            <select
              value={settings.activity_level ?? ''}
              onChange={(event) =>
                update({
                  activity_level: (event.target.value || null) as ActivityLevel | null,
                })
              }
              className={fieldClass}
              style={{ colorScheme: 'dark' }}
            >
              <option value="">Not set</option>
              {activityOptions.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <div className="text-sm sm:col-span-2">
            <span className="mb-2 block text-slate-400">Sex</span>
            <div className="flex flex-wrap gap-3">
              {sexOptions.map(({ value, label }) => (
                <label
                  key={value}
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm"
                >
                  <input
                    type="radio"
                    name="sex"
                    checked={settings.sex === value}
                    onChange={() => update({ sex: value })}
                    className="h-4 w-4 accent-emerald-500"
                  />
                  {label}
                </label>
              ))}
              {settings.sex !== null && (
                <button
                  type="button"
                  onClick={() => update({ sex: null })}
                  className="text-sm text-slate-400 hover:text-slate-200"
                >
                  Clear
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-slate-500">
              The formula we use to estimate what you burn (Mifflin-St Jeor) only
              takes male or female. That is a limit of the formula, not of you —
              the field is optional, and everything else here still works without
              it.
            </p>
          </div>

          <label className="block text-sm sm:col-span-2">
            <span className="mb-1 block text-slate-400">
              Goal rate (kg per week)
            </span>
            <input
              type="number"
              step={0.05}
              value={settings.goal_rate_kg_per_week ?? ''}
              onChange={(event) =>
                update({ goal_rate_kg_per_week: num(event.target.value) })
              }
              onBlur={guard('goal_rate_kg_per_week')}
              className={fieldClass}
            />
            <span className="mt-1 block text-xs text-slate-500">
              Negative to lose, positive to gain, 0 to maintain. Leave it blank
              and we won't guess — "not set" and "maintain" aren't the same
              answer. Anything past 1 kg/week gets capped, and we'll say so.
            </span>
          </label>
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-4 font-semibold">Daily goals</h3>

        <label className="mb-4 flex cursor-pointer items-start gap-3 rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-sm">
          <input
            type="checkbox"
            checked={settings.targets_auto}
            onChange={(event) => update({ targets_auto: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-emerald-500"
          />
          <span>
            Work out my goals from my body profile
            <span className="mt-1 block text-xs text-slate-500">
              Turning this on <strong>replaces</strong> the four goals below with
              calculated ones, and keeps updating them every time you log a
              weigh-in. Anything you typed here yourself is not kept — hit Save
              to confirm, or untick this to go back to setting them by hand.
            </span>
          </span>
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          {goalFields.filter((field) => showGoal(field.key)).map((field) => (
            <label key={field.key} className="block text-sm">
              <span className="mb-1 block text-slate-400">
                {field.label} ({field.unit})
              </span>
              <input
                type="number"
                min={1}
                value={settings[field.key]}
                readOnly={settings.targets_auto}
                onChange={(event) => update({ [field.key]: Number(event.target.value) })}
                onBlur={guard(field.key)}
                className={`w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-500 focus:outline-none ${
                  settings.targets_auto ? 'cursor-not-allowed text-slate-400' : ''
                }`}
              />
            </label>
          ))}
        </div>
        {settings.targets_auto && (
          <p className="mt-3 text-xs text-slate-500">
            Calculated from your body profile. These update on save and whenever
            you log a weigh-in.
          </p>
        )}
      </section>

      <BodyTargetsCard reloadKey={targetsKey} unit={settings.weight_unit} />

      <WaterSection settings={settings} update={update} onRejected={setRejected} />
      <StepsSection settings={settings} update={update} onRejected={setRejected} />
      {/* Last of the three trackers, and the only section here that does not
          feed the Save button below — see the note on the component. */}
      <SupplementsSection onRejected={setRejected} />

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

      <AccountSection />

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

const fieldClass =
  'w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none'

/** The step goal, and the one place the app admits there is no sync.
 *
 * A single optional input rather than water's radio pair, because the states
 * differ: water is always going to show *a* goal, so the choice is only where
 * it comes from. Steps has no derivation at all, so the choice is whether a
 * goal exists — and an empty box says that perfectly well.
 */
function StepsSection({
  settings,
  update,
  onRejected,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onRejected: (message: string) => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState('')

  const importFile = async (file: File) => {
    setImporting(true)
    setImportError('')
    setImportResult(null)
    try {
      setImportResult(await api.importStepsCsv(file))
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Import failed')
    } finally {
      setImporting(false)
      // Cleared so picking the same file again re-fires onChange.
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 font-semibold">👟 Steps</h3>
      <p className="mb-4 text-sm text-slate-400">
        Step counts are typed in by hand. Reading them from your phone or watch
        needs Health Connect or Apple Health, and neither is open to a web app
        like this one — so nothing here syncs, and it is better to say that than
        to leave you waiting for numbers that will never arrive.
      </p>

      <label className="block text-sm">
        <span className="mb-1 block text-slate-400">Daily goal</span>
        <span className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={MAX_STEPS_PER_DAY}
            value={settings.steps_goal ?? ''}
            onChange={(event) => update({ steps_goal: num(event.target.value) })}
            onBlur={() => {
              const problem = validateSettingsField(
                'steps_goal',
                settings.steps_goal,
              )
              if (!problem) return
              onRejected(problem)
              // Undone back to no goal, not to an invented one — the same
              // rule the profile fields follow, and here "unset" is a legal
              // state to land in.
              update({ steps_goal: null })
            }}
            aria-label="Daily step goal"
            className="w-28 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none"
          />
          <span className="text-xs text-slate-500">steps</span>
        </span>
      </label>
      <p className="mt-2 text-xs text-slate-500">
        Leave this empty and the card just shows your count. There is no default
        here on purpose: 10,000 is a slogan from a 1960s pedometer advert, not a
        number worked out from anything about you.
      </p>

      {/* The import sits here rather than beside the meals CSV import on
          Analytics, which costs a little consistency. It buys the thing that
          matters more: it is directly under the sentence saying entry is
          manual, which is exactly where someone thinks "can I not just upload
          this?" */}
      <div className="mt-5 border-t border-slate-800 pt-4">
        <h4 className="mb-1 text-sm font-semibold">Import a step history</h4>
        <p className="mb-3 text-xs text-slate-500">
          A CSV with a <code className="text-slate-400">date</code> column and a{' '}
          <code className="text-slate-400">steps</code> column, one row per day.
          Extra columns are ignored, so Samsung Health's{' '}
          <em>Download personal data</em> export works as it comes. Apple Health,
          Huawei Health and Health Connect each export a different format — a
          huge XML, a JSON archive and a database respectively — so those need
          converting to two columns first. Days you have already logged are kept,
          never overwritten.
        </p>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={importing}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-violet-500 hover:text-violet-300 disabled:opacity-40"
        >
          {importing ? 'Importing…' : '⬆️ Import steps (CSV)'}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(event) =>
            event.target.files?.[0] && importFile(event.target.files[0])
          }
        />
        {importResult && (
          <p className="mt-2 text-xs text-slate-400">
            Imported {importResult.inserted} day
            {importResult.inserted === 1 ? '' : 's'} — kept{' '}
            {importResult.skipped_duplicates} already logged,{' '}
            {importResult.skipped_invalid} row
            {importResult.skipped_invalid === 1 ? '' : 's'} could not be read.
          </p>
        )}
        {importError && (
          <p className="mt-2 text-xs text-rose-300">{importError}</p>
        )}
      </div>
    </section>
  )
}

/** The supplement list: add, edit, pause, delete.
 *
 * The one section on this page that saves as you go. Everything above it edits
 * a draft of the single `settings` row and waits for the Save button, but a
 * supplement is a row in its own table with its own endpoints, and holding
 * those in a draft would mean a half-typed supplement silently lost by
 * navigating away. Mixed save semantics on one page is a real cost, so the
 * header says which one this is rather than leaving it to be discovered.
 */
function SupplementsSection({
  onRejected,
}: {
  onRejected: (message: string) => void
}) {
  const [items, setItems] = useState<Supplement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState({ name: '', dose: '', times: ['08:00'] })
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    setLoading(true)
    api
      .getSupplements()
      .then((next) => {
        setItems(next)
        setError('')
      })
      // An empty list and a failed fetch look identical once rendered, and one
      // of them means "add your first" while the other means "try again".
      .catch(() => setError("Couldn't load your supplements."))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  // Opening or abandoning a form clears the last failure with it. A refusal
  // like "you already track creatine" answers the attempt that caused it, and
  // leaving it on screen once that attempt is gone makes it read as a standing
  // problem with the section rather than a rejected keystroke.
  const startAdd = () => {
    setError('')
    setDraft({ name: '', dose: '', times: ['08:00'] })
    setEditing('new')
  }

  const startEdit = (item: Supplement) => {
    setError('')
    setDraft({ name: item.name, dose: item.dose ?? '', times: [...item.times] })
    setEditing(item.id)
  }

  const cancelEdit = () => {
    setError('')
    setEditing(null)
  }

  // `map`, not an indexed assignment into a copy. Assigning past the end of a
  // shortened array leaves a hole, JSON.stringify writes the hole as `null`,
  // and the server refuses with a 422 about a field the user cannot see is
  // wrong — the exact bug the water quick-adds shipped and had to have fixed.
  // map cannot produce a hole and cannot write past the end.
  const setTime = (index: number, value: string) =>
    setDraft((current) => ({
      ...current,
      times: current.times.map((time, i) => (i === index ? value : time)),
    }))

  const removeTime = (index: number) =>
    setDraft((current) => ({
      ...current,
      times: current.times.filter((_, i) => i !== index),
    }))

  const save = async () => {
    // Empty boxes are dropped rather than sent: clearing a time input yields
    // "", which is a row the user is done with, not a time.
    const times = draft.times.filter((time) => time !== '')
    const problem = validateSupplement(draft.name, draft.dose, times)
    if (problem) {
      onRejected(problem)
      return
    }
    const body = {
      name: draft.name.trim(),
      dose: draft.dose.trim() || null,
      times,
      // Editing never changes the paused state — that is the toggle's job, and
      // a Save that silently un-paused something would be a surprise.
      active: editing === 'new'
        ? true
        : (items.find((item) => item.id === editing)?.active ?? true),
    }
    setBusy(true)
    try {
      if (editing === 'new') await api.createSupplement(body)
      else if (typeof editing === 'number') await api.updateSupplement(editing, body)
      setEditing(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const togglePause = async (item: Supplement) => {
    setBusy(true)
    try {
      await api.updateSupplement(item.id, {
        name: item.name,
        dose: item.dose,
        times: item.times,
        active: !item.active,
      })
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteSupplement(id)
      setConfirmDelete(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 font-semibold">💊 Supplements</h3>
      <p className="mb-4 text-sm text-slate-400">
        What you take, and when. Each time you add becomes a box to tick on your
        dashboard. The card will tell you when a dose is overdue while the app
        is open — and that is the whole of it:{' '}
        <strong className="text-slate-300">
          nothing here will notify you on your phone
        </strong>
        . Push notifications on Android go through Google Play Services and
        scheduled local ones need a browser feature that was never built, so a
        reminder that reached you with the app closed is not something this app
        can deliver. Changes in this section save straight away — the Save
        button below is for the settings above it.
      </p>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
            >
              {editing === item.id ? (
                <SupplementForm
                  draft={draft}
                  setDraft={setDraft}
                  setTime={setTime}
                  removeTime={removeTime}
                  onSave={save}
                  onCancel={cancelEdit}
                  busy={busy}
                />
              ) : (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  <span className={item.active ? 'text-slate-200' : 'text-slate-500'}>
                    {item.name}
                    {item.dose && (
                      <span className="ml-1.5 text-xs text-slate-500">{item.dose}</span>
                    )}
                  </span>
                  <span className="text-xs tabular-nums text-slate-500">
                    {item.times.join(' · ')}
                  </span>
                  {!item.active && (
                    <span className="rounded-full bg-slate-700/60 px-2 py-0.5 text-xs text-slate-400">
                      paused
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-2 text-xs">
                    <button
                      onClick={() => startEdit(item)}
                      disabled={busy}
                      className="text-slate-400 hover:text-emerald-300 disabled:opacity-40"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => togglePause(item)}
                      disabled={busy}
                      className="text-slate-400 hover:text-amber-300 disabled:opacity-40"
                    >
                      {item.active ? 'Pause' : 'Resume'}
                    </button>
                    {confirmDelete === item.id ? (
                      <>
                        <button
                          onClick={() => remove(item.id)}
                          disabled={busy}
                          className="rounded border border-rose-500/50 bg-rose-500/10 px-2 py-0.5 text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
                        >
                          Delete for good
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-slate-400 hover:text-slate-200"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(item.id)}
                        disabled={busy}
                        aria-label={`Delete ${item.name}`}
                        className="text-slate-500 hover:text-rose-400 disabled:opacity-40"
                      >
                        Delete
                      </button>
                    )}
                  </span>
                  {/* Spelled out rather than left to be discovered, because
                      the non-destructive option is right next to it and one of
                      the two is unrecoverable. */}
                  {confirmDelete === item.id && (
                    <p className="w-full text-xs text-rose-300">
                      Every dose you have ever ticked for {item.name} goes with
                      it. Pause instead if you are only stopping for now — that
                      keeps the history.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing === 'new' ? (
        <div className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
          <SupplementForm
            draft={draft}
            setDraft={setDraft}
            setTime={setTime}
            removeTime={removeTime}
            onSave={save}
            onCancel={cancelEdit}
            busy={busy}
          />
        </div>
      ) : (
        <button
          onClick={startAdd}
          disabled={busy || items.length >= MAX_SUPPLEMENTS}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
        >
          + Add a supplement
        </button>
      )}

      {items.length >= MAX_SUPPLEMENTS && (
        <p className="mt-2 text-xs text-slate-500">
          That is the {MAX_SUPPLEMENTS}-supplement limit — a tick list longer
          than that stops being one you can actually read every day.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
    </section>
  )
}

/** The add/edit form. One component for both, because they are the same fields
 *  and two copies would drift. */
function SupplementForm({
  draft,
  setDraft,
  setTime,
  removeTime,
  onSave,
  onCancel,
  busy,
}: {
  draft: { name: string; dose: string; times: string[] }
  setDraft: (next: { name: string; dose: string; times: string[] }) => void
  setTime: (index: number, value: string) => void
  removeTime: (index: number) => void
  onSave: () => void
  onCancel: () => void
  busy: boolean
}) {
  const field =
    'rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 focus:border-emerald-500 focus:outline-none'

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input
          value={draft.name}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          maxLength={MAX_SUPPLEMENT_NAME}
          placeholder="Name"
          aria-label="Supplement name"
          className={`${field} min-w-0 flex-1`}
        />
        <input
          value={draft.dose}
          onChange={(event) => setDraft({ ...draft, dose: event.target.value })}
          maxLength={MAX_SUPPLEMENT_DOSE}
          placeholder="Dose (optional)"
          aria-label="Dose"
          className={`${field} w-36`}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {draft.times.map((time, index) => (
          // Index as the key, unusually and deliberately: the times are edited
          // in place and two rows can legitimately hold the same value while
          // someone is mid-typing, so the value is not a stable identity.
          <span key={index} className="flex items-stretch">
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(index, event.target.value)}
              aria-label={`Time ${index + 1}`}
              style={{ colorScheme: 'dark' }}
              className={`${field} rounded-r-none`}
            />
            <button
              onClick={() => removeTime(index)}
              aria-label={`Remove time ${index + 1}`}
              className="rounded-r-lg border border-l-0 border-slate-700 px-2 text-xs text-slate-500 hover:text-rose-400"
            >
              ✕
            </button>
          </span>
        ))}
        {draft.times.length < MAX_SUPPLEMENT_TIMES && (
          <button
            onClick={() => setDraft({ ...draft, times: [...draft.times, '12:00'] })}
            className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
          >
            + time
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="text-sm text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

/** Water goal and quick-add buttons.
 *
 * The goal is a radio pair rather than a "leave blank to derive it" input,
 * because an empty box does not say what an empty box means. Choosing "from my
 * weight" writes null, which is what the server reads as "derive it".
 */
function WaterSection({
  settings,
  update,
  onRejected,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onRejected: (message: string) => void
}) {
  const derived = settings.water_goal_ml === null
  const quickAdds = settings.water_quick_adds ?? DEFAULT_WATER_QUICK_ADDS

  // A blank box drops that button rather than storing a zero, so the inputs can
  // express anywhere from one button up to MAX_WATER_QUICK_ADDS without extra
  // UI. The count comes from the constant rather than from the length of
  // DEFAULT_WATER_QUICK_ADDS, which has three entries and is where the
  // off-by-one came from: the server accepts four and the fourth box was never
  // rendered, so the last slot was unreachable from the only screen that sets
  // it.
  //
  // The list is compacted on every edit, and that is not tidiness. Assigning
  // past the end of a shorter array leaves a *hole* — clear two boxes, type
  // into the third, and you get [300, <empty>, 500]. JSON.stringify writes a
  // hole as `null`, the server refuses null for a float, and the user gets a
  // 422 they cannot act on for a field they cannot see is wrong. `filter`
  // skips holes, which is what makes this the fix rather than a workaround.
  const setQuickAdd = (index: number, raw: string) => {
    const next = [...quickAdds]
    const parsed = num(raw)
    if (parsed === null) next.splice(index, 1)
    else next[index] = parsed
    const dense = next.filter((ml) => Number.isFinite(ml))
    update({ water_quick_adds: dense.length > 0 ? dense : null })
  }

  const guardQuickAdd = (index: number) => () => {
    const problem = validateWaterQuickAdd(quickAdds[index] ?? null)
    if (!problem) return
    onRejected(problem)
    // Undone, not flagged — the same rule the profile fields follow.
    const next = [...quickAdds]
    next.splice(index, 1)
    update({ water_quick_adds: next.length > 0 ? next : null })
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 font-semibold">💧 Water</h3>
      <p className="mb-4 text-sm text-slate-400">
        The card on your dashboard. Nothing here is required — leave it alone and
        the goal follows your weight.
      </p>

      <fieldset className="mb-5 space-y-2">
        <legend className="mb-2 text-sm text-slate-400">Daily goal</legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            checked={derived}
            onChange={() => update({ water_goal_ml: null })}
            className="mt-1 accent-sky-500"
          />
          <span>
            From my weight
            <span className="mt-0.5 block text-xs text-slate-500">
              {WATER_ML_PER_KG} ml for every kg of your trend weight. A common
              rule of thumb, not a measurement — and it needs a weigh-in, so
              until then the card shows a general default and says so.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            checked={!derived}
            onChange={() => update({ water_goal_ml: 2500 })}
            className="mt-1 accent-sky-500"
          />
          <span className="flex-1">
            Set my own
            {!derived && (
              <span className="mt-1 flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={MAX_WATER_GOAL_ML}
                  value={settings.water_goal_ml ?? ''}
                  onChange={(event) =>
                    update({ water_goal_ml: num(event.target.value) })
                  }
                  onBlur={() => {
                    const problem = validateSettingsField(
                      'water_goal_ml',
                      settings.water_goal_ml,
                    )
                    if (!problem) return
                    onRejected(problem)
                    update({ water_goal_ml: 2500 })
                  }}
                  aria-label="Daily water goal in ml"
                  className="w-28 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none"
                />
                <span className="text-xs text-slate-500">ml</span>
              </span>
            )}
          </span>
        </label>
      </fieldset>

      <div>
        <p className="mb-2 text-sm text-slate-400">Quick-add buttons</p>
        <div className="flex flex-wrap items-center gap-2">
          {Array.from({ length: MAX_WATER_QUICK_ADDS }).map((_, index) => (
            <span key={index} className="flex items-center gap-1">
              <span className="text-xs text-slate-600">+</span>
              <input
                type="number"
                min={1}
                max={MAX_WATER_QUICK_ADD_ML}
                value={quickAdds[index] ?? ''}
                onChange={(event) => setQuickAdd(index, event.target.value)}
                onBlur={guardQuickAdd(index)}
                aria-label={`Quick-add button ${index + 1}, in ml`}
                className="w-20 rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
              />
            </span>
          ))}
          <span className="text-xs text-slate-500">
            ml each. Clear one to remove that button.
          </span>
        </div>
      </div>
    </section>
  )
}


function AccountSection() {
  const { user, changePassword, deleteAccount } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordStatus, setPasswordStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle')
  const [passwordError, setPasswordError] = useState('')
  const [exportError, setExportError] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteStatus, setDeleteStatus] = useState<'idle' | 'deleting' | 'error'>('idle')
  const [deleteError, setDeleteError] = useState('')

  const submitPassword = async (event: React.FormEvent) => {
    event.preventDefault()
    if (newPassword.length < 8) {
      setPasswordStatus('error')
      setPasswordError('New password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus('error')
      setPasswordError('New passwords do not match.')
      return
    }
    setPasswordStatus('saving')
    try {
      await changePassword(currentPassword, newPassword)
      setPasswordStatus('saved')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPasswordStatus('error')
      setPasswordError(err instanceof Error ? err.message : 'Password change failed')
    }
  }

  const exportAll = async () => {
    setExportError('')
    try {
      await api.downloadExportAll()
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  const submitDelete = async (event: React.FormEvent) => {
    event.preventDefault()
    setDeleteStatus('deleting')
    try {
      await deleteAccount(deletePassword)
      // AuthContext clears the user, so RequireAuth redirects to the login page.
    } catch (err) {
      setDeleteStatus('error')
      setDeleteError(err instanceof Error ? err.message : 'Account deletion failed')
    }
  }

  return (
    <>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-1 font-semibold">Account</h3>
        <p className="mb-4 text-sm text-slate-400">Signed in as {user?.email}</p>

        <form onSubmit={submitPassword} className="max-w-sm space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">New password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Confirm new password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={passwordStatus === 'saving'}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
            >
              {passwordStatus === 'saving' ? 'Changing…' : 'Change password'}
            </button>
            {passwordStatus === 'saved' && (
              <span className="text-sm text-emerald-400">Password changed ✓</span>
            )}
            {passwordStatus === 'error' && (
              <span className="text-sm text-rose-400">{passwordError}</span>
            )}
          </div>
        </form>

        <div className="mt-5 border-t border-slate-800 pt-4">
          <p className="mb-2 text-sm text-slate-400">
            Download everything stored for this account — meals, food library, saved
            meal templates, weight entries, water logs, step counts, supplements and
            the doses you ticked, body profile, goals and AI analyses — as a single
            JSON file.
          </p>
          <button
            onClick={exportAll}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300"
          >
            Download all my data (JSON)
          </button>
          {exportError && <p className="mt-2 text-sm text-rose-400">{exportError}</p>}
        </div>
      </section>

      <section className="rounded-xl border border-rose-900/60 bg-slate-900 p-5">
        <h3 className="mb-1 font-semibold text-rose-300">Danger zone</h3>
        <p className="mb-4 text-sm text-slate-400">
          Deleting your account permanently removes all meals, foods, meal templates,
          weight entries, water logs, step counts, supplements and their check-offs,
          your body profile, goals and AI analyses. This cannot be undone.
        </p>
        {!confirmingDelete ? (
          <button
            onClick={() => setConfirmingDelete(true)}
            className="rounded-lg border border-rose-700 px-4 py-2 text-sm text-rose-300 hover:bg-rose-500/10"
          >
            Delete account…
          </button>
        ) : (
          <form onSubmit={submitDelete} className="max-w-sm space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block text-slate-400">
                Enter your password to confirm
              </span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className={fieldClass}
              />
            </label>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={deleteStatus === 'deleting'}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
              >
                {deleteStatus === 'deleting'
                  ? 'Deleting…'
                  : 'Permanently delete my account'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmingDelete(false)
                  setDeletePassword('')
                  setDeleteStatus('idle')
                }}
                className="text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
            </div>
            {deleteStatus === 'error' && (
              <p className="text-sm text-rose-400">{deleteError}</p>
            )}
          </form>
        )}
      </section>
    </>
  )
}

/** Height, in whichever unit the weight preference implies.
 *
 * The API is always centimetres; feet and inches exist only here and in
 * lib/units.ts. The round trip is stable — cmToFtIn rounds to the nearest inch
 * and ftInToCm to the nearest millimetre — so this can derive the displayed
 * feet/inches from the stored cm each render instead of holding a second copy
 * of the value that could drift out of step with it. */
function HeightField({
  settings,
  update,
  onBlur,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onBlur: () => void
}) {
  if (settings.weight_unit !== 'lb') {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-400">Height (cm)</span>
        <input
          type="number"
          value={settings.height_cm ?? ''}
          onChange={(event) => update({ height_cm: num(event.target.value) })}
          onBlur={onBlur}
          className={fieldClass}
        />
      </label>
    )
  }

  const { feet, inches } = settings.height_cm
    ? cmToFtIn(settings.height_cm)
    : { feet: 0, inches: 0 }
  const set = (nextFeet: number | null, nextInches: number | null) => {
    // Both boxes empty means "not set", not "zero tall".
    if (nextFeet === null && nextInches === null) {
      update({ height_cm: null })
      return
    }
    update({ height_cm: ftInToCm(nextFeet ?? 0, nextInches ?? 0) })
  }

  return (
    <div className="text-sm">
      <span className="mb-1 block text-slate-400">Height</span>
      <div className="flex gap-2">
        <label className="flex-1">
          <input
            type="number"
            aria-label="Height, feet"
            placeholder="ft"
            value={settings.height_cm ? feet : ''}
            onChange={(event) =>
              set(num(event.target.value), settings.height_cm ? inches : null)
            }
            onBlur={onBlur}
            className={fieldClass}
          />
        </label>
        <label className="flex-1">
          <input
            type="number"
            aria-label="Height, inches"
            placeholder="in"
            value={settings.height_cm ? inches : ''}
            onChange={(event) =>
              set(settings.height_cm ? feet : null, num(event.target.value))
            }
            onBlur={onBlur}
            className={fieldClass}
          />
        </label>
      </div>
      <span className="mt-1 block text-xs text-slate-500">
        Stored in centimetres; shown in feet and inches because your weight unit
        is pounds.
      </span>
    </div>
  )
}

// Field name → what to ask the user for. Keyed on what the API returns so a
// field added server-side without a label here still shows *something*.
const missingLabels: Record<string, string> = {
  weight: 'a recent weigh-in',
  height_cm: 'your height',
  birth_date: 'your date of birth',
  sex: 'your sex',
  activity_level: 'your activity level',
  goal_rate_kg_per_week: 'a goal rate',
}

/** The derived numbers, each next to what it was computed from.
 *
 * None of these are measurements of the person, and the card should not let
 * them look like one — same principle as TrendReadout on the Weight page. The
 * weight and the date it was logged are shown because body weight is the input
 * most likely to be quietly out of date. */
function BodyTargetsCard({
  reloadKey,
  unit,
}: {
  reloadKey: number
  unit: 'kg' | 'lb'
}) {
  const [targets, setTargets] = useState<BodyTargets | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getBodyTargets()
      .then((next) => {
        if (!cancelled) {
          setTargets(next)
          setFailed(false)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  if (failed) return null
  if (!targets) {
    return (
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-1 font-semibold">What your profile works out to</h3>
        <p className="text-sm text-slate-400">Loading…</p>
      </section>
    )
  }

  const stillNeeded = targets.missing
    .map((field) => missingLabels[field] ?? field)
    .join(', ')

  const measured = targets.tdee_source === 'measured'
  const basis = targets.tdee_basis

  const rows: { label: string; value: string; caption: string }[] = [
    {
      label: 'BMI',
      value: targets.bmi === null ? '—' : targets.bmi.toFixed(1),
      caption: 'Your weight against your height. Says nothing about body composition.',
    },
    {
      label: 'Resting burn (BMR)',
      value: targets.bmr === null ? '—' : `${Math.round(targets.bmr)} kcal`,
      caption: 'Mifflin-St Jeor, from your height, weight, age and sex.',
    },
    {
      label: measured ? 'Daily burn (measured)' : 'Daily burn (estimated)',
      value: targets.tdee === null ? '—' : `${Math.round(targets.tdee)} kcal`,
      caption: measured
        ? `Measured from what you actually logged: ${basis?.logged_days} days of meals against ${basis?.weigh_ins} weigh-ins over ${basis?.span_days} days. The formula would have said ${Math.round(targets.tdee_estimated ?? 0)} kcal.`
        : 'Resting burn × a fixed multiplier for your activity level. The multiplier is a convention, and the roughest step here.',
    },
    {
      label: 'Calorie target',
      value:
        targets.target_calories === null
          ? '—'
          : `${Math.round(targets.target_calories)} kcal`,
      caption: measured
        ? 'Your measured daily burn, adjusted for the rate you asked for.'
        : 'Your daily burn, adjusted for the rate you asked for.',
    },
    {
      label: 'Macro split',
      value:
        targets.protein_g === null
          ? '—'
          : `${targets.protein_g} P · ${targets.carbs_g} C · ${targets.fat_g} F`,
      caption:
        'Protein from your body weight, fat as a quarter of calories, carbs the remainder.',
    },
    {
      label: 'Weight used',
      value:
        targets.weight_kg === null
          ? '—'
          : `${targets.weight_kg.toFixed(1)} kg`,
      caption:
        targets.weight_date === null
          ? 'No weigh-in in the last 90 days, so nothing here can be calculated.'
          : `Your smoothed trend weight as of ${targets.weight_date}.`,
    },
  ]

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 font-semibold">What your profile works out to</h3>
      <p className="mb-4 text-sm text-slate-400">
        {measured
          ? 'Your daily burn is now measured from your own logs — what you ate, ' +
            'against how your weight actually moved — rather than predicted by a ' +
            'formula. BMI and resting burn below are still formulas.'
          : 'Estimates, not measurements — a formula applied to what you typed above. ' +
            'They can be a few hundred calories out for any one person, so treat them ' +
            'as a starting point and let your own weight trend correct them.'}
        {unit === 'lb' && ' Weights here are shown in kg, as the formulas use them.'}
      </p>

      {stillNeeded && (
        <p className="mb-4 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-300">
          Add {stillNeeded} to see the rest.
        </p>
      )}

      {!measured && basis?.unavailable_reason && (
        <p className="mb-4 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-300">
          {basis.unavailable_reason}
        </p>
      )}

      {targets.clamped_reason && (
        <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          {targets.clamped_reason}
        </p>
      )}

      <dl className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label}>
            <dt className="text-xs text-slate-400">{row.label}</dt>
            <dd className="text-lg font-semibold">{row.value}</dd>
            <p className="mt-0.5 text-xs text-slate-500">{row.caption}</p>
          </div>
        ))}
      </dl>
    </section>
  )
}
