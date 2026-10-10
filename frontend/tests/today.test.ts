// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { calorieBalance, dayHeading, dayTotals, litSegments, planCaption, viewedDay } from '../src/lib/today.ts'
import type { Meal, PlanDay } from '../src/types.ts'

const meal = (calories: number, protein: number, carbs: number | null, fat: number | null): Meal => ({
  id: 1,
  date: '2026-10-10',
  name: 'x',
  calories,
  protein,
  carbs,
  fat,
  updated_at: null,
})

const plan = (over: Partial<PlanDay>): PlanDay => ({
  date: '2026-10-10',
  calorie_goal: 2400,
  protein_goal: 150,
  carbs_goal: 230,
  fat_goal: 70,
  calorie_delta: null,
  kind: null,
  event_date: null,
  ...over,
})

test('the day adds up its meals, and a missing carb or fat count is zero', () => {
  assert.deepEqual(dayTotals([]), { calories: 0, protein: 0, carbs: 0, fat: 0 })
  assert.deepEqual(dayTotals([meal(500, 30, 60, null), meal(250.5, 10, null, 9)]), {
    calories: 750.5,
    protein: 40,
    carbs: 60,
    fat: 9,
  })
})

test('a plan caption names the day it moves calories to or from', () => {
  assert.equal(planCaption(null, false), undefined)
  assert.equal(planCaption(plan({}), false), undefined)
  assert.match(planCaption(null, true) ?? '', /usual target/)
  assert.equal(
    planCaption(plan({ calorie_delta: 300, kind: 'planned', event_date: '2026-10-10' }), false),
    '+300 kcal — a day you planned for',
  )
  assert.match(
    planCaption(plan({ calorie_delta: -150.4, kind: 'planned', event_date: '2026-10-12' }), false) ?? '',
    /^−150 kcal — funding /,
  )
  assert.match(
    planCaption(plan({ calorie_delta: -100, kind: 'compensating', event_date: '2026-10-08' }), false) ?? '',
    /^−100 kcal — making up /,
  )
})

test('a gauge fills towards its goal and stops there', () => {
  assert.equal(litSegments(0, 2100, 20), 0)
  assert.equal(litSegments(1050, 2100, 20), 10)
  assert.equal(litSegments(2100, 2100, 20), 20)
  assert.equal(litSegments(3500, 2100, 20), 20)
  assert.equal(litSegments(40, 2100, 20), 0)
  assert.equal(litSegments(500, 0, 20), 0)
  assert.equal(litSegments(-5, 100, 10), 0)
})

test('the headline is always positive; over says which way', () => {
  assert.deepEqual(calorieBalance(860.4, 2100), { amount: 1240, over: false })
  assert.deepEqual(calorieBalance(2100, 2100), { amount: 0, over: false })
  assert.deepEqual(calorieBalance(2350, 2100), { amount: 250, over: true })
})

test('the viewed day is a real past date from the address, or today', () => {
  const today = '2026-10-10'
  assert.equal(viewedDay(null, today), today)
  assert.equal(viewedDay('2026-10-07', today), '2026-10-07')
  assert.equal(viewedDay('2026-10-11', today), today)
  assert.equal(viewedDay('2026-02-31', today), today)
  assert.equal(viewedDay('yesterday', today), today)
  assert.equal(viewedDay('2026-10-10', today), today)
})

test('the date control says Today and Yesterday by name', () => {
  assert.match(dayHeading('2026-10-10', '2026-10-10', '2026-10-09'), /^Today, /)
  assert.match(dayHeading('2026-10-09', '2026-10-10', '2026-10-09'), /^Yesterday, /)
  assert.doesNotMatch(dayHeading('2026-10-07', '2026-10-10', '2026-10-09'), /Today|Yesterday/)
})
