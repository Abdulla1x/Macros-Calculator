import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AlertDialog from '../components/AlertDialog'
import AccountSection from '../components/settings/AccountSection'
import BodyTargetsCard from '../components/settings/BodyTargetsCard'
import CaloriePlanSection from '../components/settings/CaloriePlanSection'
import FoodLibrarySection from '../components/settings/FoodLibrarySection'
import HeightField from '../components/settings/HeightField'
import StepsSection from '../components/settings/StepsSection'
import SupplementsSection from '../components/settings/SupplementsSection'
import WaterSection from '../components/settings/WaterSection'
import { fieldClass } from '../components/settings/fieldClass'
import { validateSettingsField } from '../lib/limits'
import { num } from '../lib/parse'
import { useSettings } from '../settings/SettingsContext'
import type {
  ActivityLevel,
  Sex,
  Settings as SettingsType,
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
  // The day the dashboard was showing when the planning link was followed, so
  // the planner opens on it rather than on today. Read from router state the
  // same way LogMeal reads `logDate`. Undefined when Settings is reached any
  // other way, which is the ordinary case.
  const planDate = (useLocation().state as { planDate?: string } | null)?.planDate
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
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-slate-400">Choose what to track and set your daily goals.</p>
      </header>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-3 font-semibold">Tracked macros</h2>
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
        <h2 className="mb-3 font-semibold">Units</h2>
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
        <h2 className="mb-1 font-semibold">Body profile</h2>
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
            />
            <span className="mt-1 block text-xs text-ink-faint">
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
            <p className="mt-2 text-xs text-ink-faint">
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
            <span className="mt-1 block text-xs text-ink-faint">
              Negative to lose, positive to gain, 0 to maintain. Leave it blank
              and we won't guess — "not set" and "maintain" aren't the same
              answer. Anything past 1 kg/week gets capped, and we'll say so.
            </span>
          </label>
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-4 font-semibold">Daily goals</h2>

        <label className="mb-4 flex cursor-pointer items-start gap-3 rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-sm">
          <input
            type="checkbox"
            checked={settings.targets_auto}
            onChange={(event) => update({ targets_auto: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-emerald-500"
          />
          <span>
            Work out my goals from my body profile
            <span className="mt-1 block text-xs text-ink-faint">
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
                className={`w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-base focus:border-emerald-500 sm:text-sm ${
                  settings.targets_auto ? 'cursor-not-allowed text-slate-400' : ''
                }`}
              />
            </label>
          ))}
        </div>
        {settings.targets_auto && (
          <p className="mt-3 text-xs text-ink-faint">
            Calculated from your body profile. These update on save and whenever
            you log a weigh-in.
          </p>
        )}
      </section>

      <BodyTargetsCard reloadKey={targetsKey} unit={settings.weight_unit} />

      <WaterSection settings={settings} update={update} onRejected={setRejected} />
      <StepsSection settings={settings} update={update} onRejected={setRejected} />
      {/* Last of the three trackers. It and the food library below are the two
          sections here that write straight away rather than feeding the Save
          button — both say so in their own copy. */}
      <SupplementsSection onRejected={setRejected} />
      <CaloriePlanSection onRejected={setRejected} initialDate={planDate} />
      <FoodLibrarySection onRejected={setRejected} />

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
