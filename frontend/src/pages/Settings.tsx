import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Settings as SettingsType } from '../types'

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

export default function Settings() {
  const [settings, setSettings] = useState<SettingsType | null>(null)
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => setError('Could not load settings.'))
  }, [])

  if (!settings) {
    return <p className="text-slate-400">{error || 'Loading…'}</p>
  }

  const update = (patch: Partial<SettingsType>) => {
    setSettings({ ...settings, ...patch })
    setStatus('idle')
  }

  const save = async () => {
    setStatus('saving')
    try {
      setSettings(await api.updateSettings(settings))
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
        <h3 className="mb-4 font-semibold">Daily goals</h3>
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
                onChange={(event) => update({ [field.key]: Number(event.target.value) })}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-500 focus:outline-none"
              />
            </label>
          ))}
        </div>
      </section>

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
    </div>
  )
}
