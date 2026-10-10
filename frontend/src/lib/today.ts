import type { Meal, PlanDay } from '../types.ts'
import { localIsoDate, parseIsoDate } from './dates.ts'

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

/** The meals a day shows, and the ones it counts, around a deletion.
 *
 *  A held meal (still undoable) is shown, struck through, and not counted. A
 *  gone meal (its delete has been sent) is neither, from the moment it is
 *  sent until the server stops returning it. The held state ends when the
 *  line has folded away, 280 ms in, while the reload that drops the meal is
 *  still on its way: without the gone set, the meal counted again in that gap
 *  and the totals dropped, came back, then dropped again (found on a phone
 *  test). */
export function shownMeals(meals: readonly Meal[], heldId: number | undefined, gone: ReadonlySet<number>): Meal[] {
  return meals.filter((meal) => meal.id === heldId || !gone.has(meal.id))
}

export function countedMeals(meals: readonly Meal[], heldId: number | undefined, gone: ReadonlySet<number>): Meal[] {
  return meals.filter((meal) => meal.id !== heldId && !gone.has(meal.id))
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

/** How many of a gauge's segments are lit. A gauge fills to its goal and no
 *  further: past the target it is simply full (DESIGN.md: over is drawn
 *  calmly, never as an alarm). No goal means nothing to fill towards. */
export function litSegments(value: number, goal: number, segments: number): number {
  if (!(goal > 0) || !(value > 0)) return 0
  return Math.round((Math.min(value, goal) / goal) * segments)
}

/** The headline number: calories left, or by how much the day went over. The
 *  number shown is always positive; `over` says which word goes above it. */
export function calorieBalance(eaten: number, target: number): { amount: number; over: boolean } {
  const left = Math.round(target) - Math.round(eaten)
  return { amount: Math.abs(left), over: left < 0 }
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

/** The day Today shows, from the address's `?day=`. Anything that is not a
 *  real past date (a typo, a future day, a hand-edited link) shows today
 *  instead of an error: the page always has a day to show. */
export function viewedDay(param: string | null, today: string): string {
  if (!param || !ISO_DAY.test(param) || param >= today) return today
  // 2026-02-31 parses, and rolls over to March: not a real day.
  return localIsoDate(parseIsoDate(param)) === param ? param : today
}

/** The date control's words: "Today, Sat 10 Oct", "Yesterday, Fri 9 Oct",
 *  or just "Wed 7 Oct" further back. */
export function dayHeading(day: string, today: string, yesterday: string): string {
  const date = parseIsoDate(day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  if (day === today) return `Today, ${date}`
  if (day === yesterday) return `Yesterday, ${date}`
  return date
}

/** Which characters of a number changed, for rolling only those
 *  (DESIGN.md Motion: only the digits that changed roll into place,
 *  staggered from the right). The two strings are compared right-aligned, so
 *  "980" to "1,020" compares units with units. One entry per character of
 *  `next`, left to right: null if it is the same as before, otherwise its turn
 *  in the stagger, 0 for the rightmost change. */
export function changedDigits(prev: string, next: string): (number | null)[] {
  const turns: (number | null)[] = new Array<number | null>(next.length).fill(null)
  let turn = 0
  for (let fromRight = 0; fromRight < next.length; fromRight += 1) {
    const index = next.length - 1 - fromRight
    if (next[index] !== prev[prev.length - 1 - fromRight]) {
      turns[index] = turn
      turn += 1
    }
  }
  return turns
}

/** The time shown on a meal row, or null for none (decided 2026-10-10).
 *
 *  It is when the meal was LOGGED, the only time the app records, so it is
 *  shown only beside a meal logged on the day it was eaten, where the two are
 *  close. A meal entered on a later day shows nothing rather than a time that
 *  would be wrong (yesterday's dinner at "09:05"), and so does a meal from
 *  before the server kept the time, or anyone who switched it off. */
export function mealTimeLabel(meal: Pick<Meal, 'date' | 'created_at'>, show: boolean): string | null {
  if (!show || !meal.created_at) return null
  const logged = new Date(meal.created_at)
  if (Number.isNaN(logged.getTime()) || localIsoDate(logged) !== meal.date) return null
  return logged.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}
