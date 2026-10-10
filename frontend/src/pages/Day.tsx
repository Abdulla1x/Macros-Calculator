import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import ScreenBar from '../components/shell/ScreenBar'
import { addDays, localIsoDate } from '../lib/dates'
import { calorieBalance, dayHeading, dayTotals, planCaption, viewedDay } from '../lib/today'
import { useSettings } from '../settings/SettingsContext'
import { useLiveMessage } from '../hooks/useLiveMessage'
import type { Meal, PlanDay } from '../types'
import Block from '@/ui/block'
import { RowLink } from '@/ui/row'
import { Stat, StatGrid } from '@/ui/stat'

const n = (value: number) => Math.round(value).toLocaleString()

/** The day in detail: what the calories band opens (DESIGN.md: "Tap: opens the
 *  day in detail, with calorie plans"). The band keeps one headline; the rest
 *  of the day's numbers, and the way into calorie plans, live one tap behind
 *  it. Calorie plans have never been used on any account, so they stay here
 *  rather than on Today (0a: "one tap behind the calories hero, without more
 *  prominence").
 *
 *  No measured daily burn here: the endpoint for it has no date, so on a past
 *  day it would show today's figure under that day's name. */
export default function Day() {
  const { settings } = useSettings()
  const today = localIsoDate()
  const day = viewedDay(useParams().date ?? null, today)
  const [meals, setMeals] = useState<Meal[] | null>(null)
  const [plan, setPlan] = useState<PlanDay | null>(null)
  const [planFailed, setPlanFailed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useLiveMessage(error)

  const load = useCallback(() => {
    setError(null)
    api
      .getMeals(day)
      .then(setMeals)
      .catch(() => setError("Couldn't load this day. Check your connection, then try again."))
    // The targets in force that day, plan included; resolved by the server,
    // as on Today. A failure falls back to the usual goals and says so.
    api
      .getPlanDay(day)
      .then((next) => {
        setPlan(next)
        setPlanFailed(false)
      })
      .catch(() => {
        setPlan(null)
        setPlanFailed(true)
      })
  }, [day])

  useEffect(load, [load])

  const goals = plan?.date === day ? plan : settings
  const eaten = dayTotals(meals ?? [])
  const balance = goals ? calorieBalance(eaten.calories, goals.calorie_goal) : null
  const caption = planCaption(plan?.date === day ? plan : null, planFailed)
  const plansLink = (kind: 'planned' | 'compensating') => `/settings/goals?plan=${day}&kind=${kind}`

  return (
    <div className="mx-auto grid max-w-[760px] grid-cols-[minmax(0,1fr)]">
      <ScreenBar
        title={dayHeading(day, today, addDays(today, -1))}
        back={day === today ? '/' : `/?day=${day}`}
        backLabel="Back to Today"
      />

      <Block label="The day in numbers" value={meals ? `${meals.length} ${meals.length === 1 ? 'meal' : 'meals'}` : undefined}>
        {error ? (
          <p role="alert" className="border-l-2 border-ink pl-3 text-small">
            {error}{' '}
            <button type="button" onClick={load} className="font-semibold underline underline-offset-3">
              Retry
            </button>
          </p>
        ) : !meals || !goals || !settings || !balance ? (
          <div aria-hidden="true" className="grid grid-cols-2 gap-4 py-2.5">
            {[0, 1, 2, 3].map((key) => (
              <span key={key} className="h-[52px] rounded-control bg-track motion-safe:animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            <StatGrid>
              <Stat label="Eaten" unit="kcal">
                {n(eaten.calories)}
              </Stat>
              <Stat label="Target" unit="kcal">
                {n(goals.calorie_goal)}
              </Stat>
              <Stat label={balance.over ? 'Over' : 'Left'} unit="kcal">
                {n(balance.amount)}
              </Stat>
              <Stat label="Protein" unit={`/ ${n(goals.protein_goal)} g`}>
                {n(eaten.protein)}
              </Stat>
              {settings.track_carbs && (
                <Stat label="Carbs" unit={`/ ${n(goals.carbs_goal)} g`}>
                  {n(eaten.carbs)}
                </Stat>
              )}
              {settings.track_fat && (
                <Stat label="Fat" unit={`/ ${n(goals.fat_goal)} g`}>
                  {n(eaten.fat)}
                </Stat>
              )}
            </StatGrid>
            {caption && <p className="text-small text-ink-2">{caption}</p>}
            {balance.over && (
              <p className="text-small text-ink-2">Over is fine. The week evens out, or make it up below.</p>
            )}
          </>
        )}
      </Block>

      <Block label="Calorie plans">
        <p className="text-small text-ink-2">
          Move calories between days: a bigger day paid for by the days around it, or a day that ran over spread
          across the next few.
        </p>
        <div className="divide-y divide-rule">
          <RowLink to={plansLink('planned')} label="Plan a bigger day" detail="Fund a dinner out from the days around it" />
          <RowLink to={plansLink('compensating')} label="Make up a day" detail="Move what ran over onto the next few days" />
        </div>
      </Block>
    </div>
  )
}
