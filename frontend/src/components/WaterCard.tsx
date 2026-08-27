import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import {
  DEFAULT_WATER_QUICK_ADDS,
  MAX_WATER_ENTRY_ML,
  WATER_ML_PER_KG,
} from '../lib/limits'
import { useSettings } from '../settings/SettingsContext'
import { trackerHues } from '../lib/chartTheme'
import type { WaterDay } from '../types'
import DailyTrackerCard from './DailyTrackerCard'
import Card from './ui/Card'

interface Props {
  /** The day being viewed on the dashboard, not necessarily today. */
  date: string
}

export default function WaterCard({ date }: Props) {
  const { settings } = useSettings()
  const [day, setDay] = useState<WaterDay | null>(null)
  const [custom, setCustom] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api
      .getWaterDay(date)
      .then((next) => {
        setDay(next)
        setError(null)
      })
      // A failed load must not render as a day with nothing logged — the same
      // rule the meal list follows.
      .catch(() => setError("Couldn't load your water for this day."))
  }, [date])

  useEffect(() => {
    load()
  }, [load])

  const quickAdds = settings?.water_quick_adds ?? DEFAULT_WATER_QUICK_ADDS

  const add = async (ml: number) => {
    setBusy(true)
    try {
      await api.addWater(date, ml)
      setError(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const addCustom = async () => {
    const ml = Number(custom)
    // Refused here rather than at the server, for the reason limits.ts exists:
    // a value the API is certain to reject should never look accepted.
    if (!Number.isFinite(ml) || ml <= 0) {
      setError('Enter an amount in ml, greater than zero.')
      return
    }
    if (ml > MAX_WATER_ENTRY_ML) {
      setError(`That is more than ${MAX_WATER_ENTRY_ML.toLocaleString()} ml in one go — split it up.`)
      return
    }
    await add(ml)
    setCustom('')
  }

  // Undo removes the most recent entry. The server returns entries newest
  // first precisely so this needs no sorting.
  const undo = async () => {
    const last = day?.entries[0]
    if (!last) return
    setBusy(true)
    try {
      await api.deleteWaterEntry(last.id)
      setError(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not undo that — try again.')
    } finally {
      setBusy(false)
    }
  }

  if (!day) {
    return (
      <Card>
        <h2 className="font-semibold">
          <span className="mr-2">💧</span>Water
        </h2>
        <p className="mt-3 text-xs text-ink-faint">
          {error ?? 'Loading…'}
        </p>
      </Card>
    )
  }

  // Bound once so the guard below and the value it protects are the same read.
  // `day.entries.length > 0` told the compiler nothing about `day.entries[0]`.
  const lastEntry = day.entries[0]

  return (
    <DailyTrackerCard
      icon="💧"
      label="Water"
      value={day.total_ml}
      goal={day.goal_ml}
      unit="ml"
      color={trackerHues.water}
      error={error}
      caption={<GoalCaption day={day} />}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {quickAdds.map((ml) => (
            <button
              key={ml}
              onClick={() => add(ml)}
              disabled={busy}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-sky-500 hover:text-sky-300 disabled:opacity-40"
            >
              +{ml}
            </button>
          ))}
          <div className="flex items-stretch">
            <input
              type="number"
              inputMode="numeric"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addCustom()
                }
              }}
              placeholder="ml"
              aria-label="Custom amount in ml"
              className="w-20 rounded-l-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-base sm:text-sm text-slate-200"
            />
            <button
              onClick={addCustom}
              disabled={busy || custom.trim() === ''}
              className="rounded-r-lg border border-l-0 border-slate-700 px-2.5 text-sm text-slate-400 hover:text-sky-300 disabled:opacity-40"
            >
              Add
            </button>
          </div>
          {lastEntry && (
            <button
              onClick={undo}
              disabled={busy}
              className="ml-auto text-xs text-ink-faint hover:text-slate-300 disabled:opacity-40"
            >
              Undo last (−{Math.round(lastEntry.ml)})
            </button>
          )}
        </div>
      }
    />
  )
}

/** The derivation, in the open.
 *
 * The standing rule is that no derived number reaches the screen without its
 * inputs beside it — and the "default" case matters most, because 2 litres
 * looks personal and isn't. */
function GoalCaption({ day }: { day: WaterDay }) {
  const { source, ml_per_kg, weight_kg } = day.goal_basis

  if (source === 'custom') {
    return <>Goal set by you, in Settings.</>
  }
  if (source === 'weight' && ml_per_kg != null && weight_kg != null) {
    return (
      <>
        Goal = {ml_per_kg} ml × {weight_kg.toFixed(1)} kg trend weight, rounded.
        A rule of thumb, not a measurement.
      </>
    )
  }
  return (
    <>
      A general default — log a weigh-in and this becomes {' '}
      {WATER_ML_PER_KG} ml per kg of your own weight instead.
    </>
  )
}
