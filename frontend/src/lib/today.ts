import type { Meal, PlanDay } from '../types.ts'
import { parseIsoDate } from './dates.ts'

/** The arithmetic behind Today, kept apart from the page so it can be tested
 *  without a browser. Nothing in here draws anything. */

export interface DayTotals {
  calories: number
  protein: number
  carbs: number
  fat: number
}

/** What the day's meals add up to. A meal with no carbs or fat recorded counts
 *  as zero towards them, as it always has on this screen. */
export function dayTotals(meals: readonly Meal[]): DayTotals {
  return meals.reduce<DayTotals>(
    (sum, meal) => ({
      calories: sum.calories + meal.calories,
      protein: sum.protein + meal.protein,
      carbs: sum.carbs + (meal.carbs ?? 0),
      fat: sum.fat + (meal.fat ?? 0),
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 },
  )
}

/** What the caption under the calories says, if anything.
 *
 *  Only calories get one. Protein does not move under a plan at all, and
 *  captioning carbs and fat with the same sentence would be noise around a
 *  fact that belongs to the day, not to each macro. */
export function planCaption(plan: PlanDay | null, failed: boolean): string | undefined {
  if (failed) {
    return "Couldn't check for a plan on this day — showing your usual target."
  }
  if (!plan || plan.calorie_delta === null) return undefined

  const sign = plan.calorie_delta > 0 ? '+' : '−'
  const moved = `${sign}${Math.abs(Math.round(plan.calorie_delta))} kcal`
  // The event day of a planned group is one of its own adjusted days, so this
  // is the day being planned for rather than a day funding one.
  if (plan.event_date === plan.date) return `${moved} — a day you planned for`

  const when = plan.event_date
    ? parseIsoDate(plan.event_date).toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })
    : null
  if (!when) return moved
  return plan.kind === 'planned' ? `${moved} — funding ${when}` : `${moved} — making up ${when}`
}
