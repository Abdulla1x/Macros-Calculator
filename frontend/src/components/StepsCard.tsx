import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { MAX_STEPS_PER_DAY } from '../lib/limits'
import type { StepDay } from '../types'
import DailyTrackerCard from './DailyTrackerCard'

interface Props {
  /** The day being viewed on the dashboard, not necessarily today. */
  date: string
}

export default function StepsCard({ date }: Props) {
  const [day, setDay] = useState<StepDay | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api
      .getStepDay(date)
      .then((next) => {
        setDay(next)
        // The input starts from what is stored, because the interaction here is
        // *correcting* a number rather than adding to one — the whole reason
        // this is an upsert and water is not.
        setDraft(next.logged ? String(next.steps) : '')
        setError(null)
      })
      // A failed load must not render as a day with nothing logged — the same
      // rule the water card and the meal list follow.
      .catch(() => setError("Couldn't load your steps for this day."))
  }, [date])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    const steps = Number(draft)
    // Refused here rather than at the server, for the reason limits.ts exists:
    // a value the API is certain to reject should never look accepted.
    if (draft.trim() === '' || !Number.isFinite(steps) || steps < 0) {
      setError('Enter a step count of zero or more.')
      return
    }
    if (!Number.isInteger(steps)) {
      setError('Steps are whole numbers.')
      return
    }
    if (steps > MAX_STEPS_PER_DAY) {
      setError(
        `${MAX_STEPS_PER_DAY.toLocaleString()} steps is already further than anyone walks in a day — check for a stray digit.`,
      )
      return
    }
    setBusy(true)
    try {
      await api.saveSteps(date, steps)
      setError(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  // Clearing is not the same as saving a zero: zero says "I did not walk",
  // this says "this day should not have a count on it at all".
  const clear = async () => {
    setBusy(true)
    try {
      await api.clearSteps(date)
      setError(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not clear that — try again.')
    } finally {
      setBusy(false)
    }
  }

  if (!day) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">
          <span className="mr-2">👟</span>Steps
        </h3>
        <p className="mt-3 text-xs text-ink-faint">{error ?? 'Loading…'}</p>
      </div>
    )
  }

  return (
    <DailyTrackerCard
      icon="👟"
      label="Steps"
      value={day.steps}
      goal={day.goal}
      unit="steps"
      color="#a78bfa"
      error={error}
      caption={<StepsCaption day={day} />}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-stretch">
            <input
              type="number"
              inputMode="numeric"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  save()
                }
              }}
              placeholder="steps"
              aria-label="Step count for this day"
              className="w-24 rounded-l-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
            />
            <button
              onClick={save}
              disabled={busy || draft.trim() === ''}
              className="rounded-r-lg border border-l-0 border-slate-700 px-2.5 text-sm text-slate-400 hover:text-violet-300 disabled:opacity-40"
            >
              Save
            </button>
          </div>
          {day.logged && (
            <button
              onClick={clear}
              disabled={busy}
              className="ml-auto text-xs text-ink-faint hover:text-slate-300 disabled:opacity-40"
            >
              Clear this day
            </button>
          )}
        </div>
      }
    />
  )
}

/** What the number means, and — just as importantly — what it does not.
 *
 * The estimate arrives with the weight it was worked out from, the standing
 * rule for every derived number in this app. The sentence about targets is
 * there because "I walked 12,000 steps, why has my calorie goal not gone up"
 * is the obvious question, and the honest answer is that a measured daily burn
 * already contains those steps.
 */
function StepsCaption({ day }: { day: StepDay }) {
  if (day.goal === null) {
    return (
      <>
        No step goal set — you can pick one in Settings. There is no sensible
        way to work one out from your body, so this app will not invent it.
      </>
    )
  }
  if (day.burn_kcal != null && day.burn_weight_kg != null) {
    return (
      <>
        Roughly {Math.round(day.burn_kcal).toLocaleString()} kcal of walking, at{' '}
        {day.burn_weight_kg.toFixed(1)} kg. A rule of thumb, and it does not
        change your calorie target — a measured daily burn already counts it.
      </>
    )
  }
  return <>Log a weigh-in and this will also estimate what the walking cost.</>
}
