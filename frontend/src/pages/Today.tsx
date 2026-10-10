import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import CaloriesBand from '../components/today/CaloriesBand'
import DateBar from '../components/today/DateBar'
import ShareCodePanel from '../components/ShareCodePanel'
import StepsCard from '../components/StepsCard'
import SupplementsCard from '../components/SupplementsCard'
import WaterCard from '../components/WaterCard'
import { localIsoDate, parseIsoDate } from '../lib/dates'
import { dayTotals, planCaption, viewedDay } from '../lib/today'
import { useSettings } from '../settings/SettingsContext'
import { useLogPanel } from '../components/log/useLogPanel'
import { onMealsChanged } from '../lib/mealEvents'
import type { Meal, PlanDay } from '../types'
import Card from '../components/ui/Card'
import { useLiveMessage } from '../hooks/useLiveMessage'

export default function Today() {
  const { settings } = useSettings()
  const [meals, setMeals] = useState<Meal[]>([])
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  // Lifted here rather than held per-row so only one panel is ever open,
  // the same reason confirmDelete above is a single id and not a set.
  const [shareCode, setShareCode] = useState<{ label: string; code: string } | null>(
    null,
  )
  const [shareError, setShareError] = useState<string | null>(null)
  useLiveMessage(shareError)
  const [error, setError] = useState<string | null>(null)
  useLiveMessage(error)
  const [planDay, setPlanDay] = useState<PlanDay | null>(null)
  const [planFailed, setPlanFailed] = useState(false)
  // The day on show lives in the address (`?day=`, absent for today), so it
  // survives opening a meal and coming back, a reload, and the back button.
  // The Log panel's own `date` parameter is a different one: which day a new
  // meal is for.
  const [searchParams, setSearchParams] = useSearchParams()
  const [realToday, setRealToday] = useState(localIsoDate)
  const viewedDate = viewedDay(searchParams.get('day'), realToday)
  const isToday = viewedDate === realToday
  // Replace rather than push: stepping back through a week should not leave a
  // week of history entries for the back button to walk through again.
  const showDay = (day: string) =>
    setSearchParams(
      (params) => {
        if (day >= localIsoDate()) params.delete('day')
        else params.set('day', day)
        return params
      },
      { replace: true },
    )
  // The Log panel opens over this page. A meal logged from here is for the day
  // being viewed, so a tap while looking at yesterday lands on yesterday; today
  // is the panel's default and is left out of the address.
  const { open: openLog } = useLogPanel()
  const forDay = isToday ? null : viewedDate

  // Past midnight, "today" moves on. A page showing today (no `?day=`) follows
  // it when the tab regains focus; a day picked on purpose is in the address
  // and stays put. Same-string updates are no-ops.
  useEffect(() => {
    const refresh = () => setRealToday(localIsoDate())
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])

  const load = useCallback(() => {
    setError(null)
    // A failed load must not masquerade as an empty day.
    api.getMeals(viewedDate).then(setMeals).catch(() => {
      setMeals([])
      setError("Couldn't load your meals — check your connection and try again.")
    })
    // The targets actually in force on the viewed day. These are NOT
    // settings.calorie_goal: a calorie plan adjusts a single day, and the
    // server composes the adjustment on top of the stored goals. Resolved
    // there and never recomputed here -- a second definition of these numbers
    // in the client is a second thing that can be wrong, and this one would be
    // wrong invisibly, as a gauge quietly drawn against the wrong target.
    api
      .getPlanDay(viewedDate)
      .then((day) => {
        setPlanDay(day)
        setPlanFailed(false)
      })
      .catch(() => {
        // Falls back to the stored goals, and SAYS SO under the gauge. A gauge
        // silently drawn against a target that may be wrong is the kind of
        // wrong nobody reports, because nothing about it looks wrong.
        setPlanDay(null)
        setPlanFailed(true)
      })
  }, [viewedDate])

  useEffect(() => {
    load()
  }, [load])

  // A save in the Log panel happens over this page, which never remounts.
  useEffect(() => onMealsChanged(load), [load])

  const remove = async (id: number) => {
    try {
      await api.deleteMeal(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed — try again.')
      return
    } finally {
      setConfirmDelete(null)
    }
    load()
  }

  // Minted on demand rather than alongside every meal in the list: a code is
  // derived from a row, so there is nothing to cache and nothing to keep in
  // sync when the row changes.
  const showCode = async (label: string, mint: () => Promise<{ code: string }>) => {
    setShareError(null)
    try {
      setShareCode({ label, code: (await mint()).code })
    } catch (err) {
      setShareCode(null)
      setShareError(err instanceof Error ? err.message : 'Could not make a code.')
    }
  }

  const consumed = dayTotals(meals)

  // Checked at render rather than trusted from state. Two day-switches in
  // quick succession can land their responses out of order, and the late one
  // would otherwise draw this day's gauge against the other day's target --
  // silently, since a gauge gives no sign which day it was told about. The
  // stale value is dropped instead, and the goals fall back for the moment it
  // takes the right response to arrive.
  const dayPlan = planDay?.date === viewedDate ? planDay : null
  const goals = dayPlan ?? settings


  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 desk:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] desk:gap-x-10">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 desk:col-span-2">
        <DateBar day={viewedDate} today={realToday} onChange={showDay} />
        {settings && goals && (
          <CaloriesBand
            day={viewedDate}
            eaten={consumed}
            targets={goals}
            caption={planCaption(dayPlan, planFailed)}
            trackCarbs={settings.track_carbs}
            trackFat={settings.track_fat}
          />
        )}
      </div>

      <div className="grid content-start grid-cols-[minmax(0,1fr)] gap-4">
      {/* Directly above the meal list, which is now its only trigger on this
          page: template sharing moved to Settings -> Library along with the
          rest of template management. */}
      {shareError && (
        <Card as="p" tone="error" pad="sm" className="text-sm">
          {shareError}
        </Card>
      )}
      {shareCode && (
        <ShareCodePanel
          label={shareCode.label}
          code={shareCode.code}
          onClose={() => setShareCode(null)}
        />
      )}

        <Card>
          <h2 className="mb-3 font-semibold">
            {isToday
              ? "Today's meals"
              : `Meals · ${parseIsoDate(viewedDate).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}`}
          </h2>
          {error && (
            <p className="mb-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
              {error}{' '}
              <button onClick={load} className="underline hover:text-rose-200">
                Retry
              </button>
            </p>
          )}
          {meals.length === 0 ? (
            !error && (
              <p className="py-6 text-center text-sm text-ink-faint">
                Nothing logged yet —{' '}
                <button
                  type="button"
                  onClick={() => openLog('start', { date: forDay })}
                  className="text-emerald-400 underline"
                >
                  log your first meal
                </button>
                .
              </p>
            )
          ) : (
            <ul className="divide-y divide-slate-800">
              {meals.map((meal) => (
                <li key={meal.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div>
                    <p className="text-sm font-medium">{meal.name}</p>
                    <p className="text-xs text-slate-400">
                      {Math.round(meal.calories)} kcal · {Math.round(meal.protein)} g protein
                      {settings?.track_carbs && meal.carbs != null && ` · ${Math.round(meal.carbs)} g carbs`}
                      {settings?.track_fat && meal.fat != null && ` · ${Math.round(meal.fat)} g fat`}
                    </p>
                  </div>
                  {confirmDelete === meal.id ? (
                    <span className="flex items-center gap-2 text-xs">
                      <button onClick={() => remove(meal.id)} className="rounded bg-rose-500/20 px-2 py-1 text-rose-300 hover:bg-rose-500/30">
                        Delete
                      </button>
                      <button onClick={() => setConfirmDelete(null)} className="rounded bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700">
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <span className="flex items-center gap-3">
                      {/* Named by the meal, for the reason Weight's row pair is:
                          a button's contents win the accessible name whenever
                          they are non-empty, so `title` was never read and all
                          three announced as their glyph -- once per meal on the
                          list. */}
                      <button
                        onClick={() =>
                          showCode(meal.name, () => api.shareMeal(meal.id))
                        }
                        className="text-xs text-ink-faint hover:text-emerald-400"
                        aria-label={`Copy ${meal.name} as a code`}
                      >
                        <span aria-hidden="true">📋</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => openLog('hand', { date: null, state: { editMeal: meal } })}
                        className="text-xs text-ink-faint hover:text-emerald-400"
                        aria-label={`Edit ${meal.name}`}
                      >
                        <span aria-hidden="true">✎</span>
                      </button>
                      <button
                        onClick={() => setConfirmDelete(meal.id)}
                        className="text-xs text-ink-faint hover:text-rose-400"
                        aria-label={`Delete ${meal.name}`}
                      >
                        <span aria-hidden="true">✕</span>
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

      </div>

      {/* The three daily trackers.

          The right-hand column from 900px, below the meals on a phone. They
          sit below the calories because those are the primary targets, and
          below the meal list because that is what you came to read. These three
          are a glance, and a glance is what goes last. It used to sit ABOVE the
          meal list, which is how a phone ended up asking for five screens of
          scrolling before it would show you what you had eaten.

          NOTE this block used to describe itself as "the daily quick-logs",
          one word away from a dashboard card then called "Quick log" — two
          different features with nearly the same name in one file. That card is
          now "Saved meals", which settles it from the other end: these are
          trackers, and the thing that logs meals is named after meals.

          `viewedDate`, not today: the date bar's ◀ ▶ already move the whole page
          through time, and a tracker that ignored them would be the only part
          of this screen showing a different day from the rest. */}
      <section aria-label="Trackers" className="grid content-start grid-cols-[minmax(0,1fr)] gap-4">
        <WaterCard date={viewedDate} />
        <StepsCard date={viewedDate} />
        {/* Renders nothing until there is a supplement to tick, so the grid is
            two cards long for an account that has not set any up. The entry
            point is Settings; a permanent empty card would spend prime space
            explaining a feature once. */}
        <SupplementsCard date={viewedDate} />
      </section>
    </div>
  )
}
