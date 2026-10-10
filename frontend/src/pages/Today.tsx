import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import CaloriesBand from '../components/today/CaloriesBand'
import DateBar from '../components/today/DateBar'
import MealList from '../components/today/MealList'
import ReviewCard from '../components/today/ReviewCard'
import WeighInCard from '../components/today/WeighInCard'
import StepsCard from '../components/StepsCard'
import SupplementsCard from '../components/SupplementsCard'
import WaterCard from '../components/WaterCard'
import { localIsoDate } from '../lib/dates'
import { isReviewDay } from '../lib/review'
import { countedMeals, dayTotals, planCaption, shownMeals, viewedDay } from '../lib/today'
import { useSettings } from '../settings/SettingsContext'
import { useLogPanel } from '../components/log/useLogPanel'
import { onMealsChanged } from '../lib/mealEvents'
import type { Meal, PlanDay } from '../types'
import { useHeldDelete } from '../hooks/useHeldDelete'
import { useLiveMessage } from '../hooks/useLiveMessage'
import { useToast } from '../ui/toast'

export default function Today() {
  const { settings } = useSettings()
  // Null until the day's first answer: an empty list and "not loaded yet"
  // must not look alike, or every load opens on "Nothing logged yet".
  const [meals, setMeals] = useState<Meal[] | null>(null)
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
      setMeals(null)
      setError("Couldn't load your meals. Check your connection, then try again.")
    })
  }, [viewedDate])

  // The targets actually in force on the viewed day. These are NOT
  // settings.calorie_goal: a calorie plan adjusts a single day, and the
  // server composes the adjustment on top of the stored goals. Resolved
  // there and never recomputed here -- a second definition of these numbers
  // in the client is a second thing that can be wrong, and this one would be
  // wrong invisibly, as a gauge quietly drawn against the wrong target.
  //
  // Fetched again whenever the stored goals change, not only per day: a
  // weigh-in saved from this page rewrites them when targets are worked out
  // automatically, and the band must follow without a reload.
  const storedGoals = settings
    ? `${settings.calorie_goal}/${settings.protein_goal}/${settings.carbs_goal}/${settings.fat_goal}`
    : ''
  useEffect(() => {
    // Only the latest request may answer: two goal changes in quick
    // succession must not let the older response land last.
    let live = true
    api
      .getPlanDay(viewedDate)
      .then((day) => {
        if (!live) return
        setPlanDay(day)
        setPlanFailed(false)
      })
      .catch(() => {
        if (!live) return
        // Falls back to the stored goals, and SAYS SO under the gauge. A gauge
        // silently drawn against a target that may be wrong is the kind of
        // wrong nobody reports, because nothing about it looks wrong.
        setPlanDay(null)
        setPlanFailed(true)
      })
    return () => {
      live = false
    }
  }, [viewedDate, storedGoals])

  useEffect(() => {
    load()
  }, [load])

  // A save in the Log panel happens over this page, which never remounts.
  useEffect(() => onMealsChanged(() => load()), [load])

  // Delete and Undo (DESIGN.md). The meal screen's Delete comes back here
  // with the meal in router state; it is held, struck through, for ten
  // seconds before anything is sent (hooks/useHeldDelete.ts).
  // A refused delete is reported in a toast, not in the list's error slot:
  // that slot replaces the whole list, and the reload below clears it in the
  // same moment anyway, which is how the message used to vanish unseen. The
  // reload puts the meal back, so the toast and the list agree.
  const toast = useToast()
  const { held, gone, hold, undo, prune } = useHeldDelete((failure) => {
    if (failure) toast.show({ text: failure })
    load()
  })
  useEffect(() => {
    if (meals) prune(meals)
  }, [meals, prune])
  const [heldNote, setHeldNote] = useState<string | null>(null)
  useLiveMessage(heldNote)
  const location = useLocation()
  const navigate = useNavigate()
  const arriving = (location.state as { deleteMeal?: Meal } | null)?.deleteMeal
  useEffect(() => {
    if (!arriving) return
    hold(arriving)
    setHeldNote(`Deleted "${arriving.name}". Undo is there for ten seconds.`)
    // Spent: a reload or the back button must not delete it a second time.
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null })
  }, [arriving, hold, navigate, location.pathname, location.search])

  // Out of the totals the moment it is deleted, not ten seconds later, and
  // kept out until the server stops returning it.
  const consumed = dayTotals(countedMeals(meals ?? [], held?.meal.id, gone))

  // Checked at render rather than trusted from state. Two day-switches in
  // quick succession can land their responses out of order, and the late one
  // would otherwise draw this day's gauge against the other day's target --
  // silently, since a gauge gives no sign which day it was told about. The
  // stale value is dropped instead, and the goals fall back for the moment it
  // takes the right response to arrive.
  const dayPlan = planDay?.date === viewedDate ? planDay : null
  const goals = dayPlan ?? settings


  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-y-2 desk:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] desk:gap-x-10 desk:gap-y-4">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 desk:col-span-2">
        <DateBar day={viewedDate} today={realToday} onChange={showDay} />
        {!settings || !goals || meals === null ? (
          <div aria-hidden="true" className="-mx-4 h-[226px] bg-track/40 motion-safe:animate-pulse desk:mx-0 desk:h-[274px]" />
        ) : (
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

      <MealList
        meals={meals && shownMeals(meals, held?.meal.id, gone)}
        error={error}
        onRetry={load}
        isToday={isToday}
        showTimes={settings?.show_meal_times ?? true}
        trackCarbs={settings?.track_carbs ?? false}
        trackFat={settings?.track_fat ?? false}
        onLog={() => openLog('start', { date: forDay })}
        held={
          held && {
            ...held,
            onUndo: () => {
              undo()
              setHeldNote(`"${held.meal.name}" is back.`)
            },
          }
        }
      />

      {/* The daily trackers, one per row, full width (0a).

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
      <div className="grid content-start grid-cols-[minmax(0,1fr)]">
        {/* Above the trackers on review day only (Mondays, owner 2026-10-10),
            and only while looking at today. */}
        {isToday && isReviewDay(realToday) && <ReviewCard today={realToday} />}
        {/* First: the one tracker every account has, and the one with a
            reminder. */}
        <WeighInCard day={viewedDate} today={realToday} />
        <WaterCard date={viewedDate} />
        <StepsCard date={viewedDate} />
        {/* Renders nothing until there is a supplement to tick, so the grid is
            two cards long for an account that has not set any up. The entry
            point is Settings; a permanent empty card would spend prime space
            explaining a feature once. */}
        <SupplementsCard date={viewedDate} />
      </div>
    </div>
  )
}
