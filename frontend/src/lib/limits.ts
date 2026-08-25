// Client-side mirrors of the bounds in backend/app/schemas.py.
//
// Duplicated deliberately, the way MealAnalyzer mirrors the server's
// MAX_IMAGES: the server stays the authority and still rejects anything out of
// range, but a value the API is certain to refuse should never be accepted by
// the form in the first place. A user who types a number, watches it sit there
// looking accepted, and only finds out when Save fails has been misled by the
// UI — and the explanation of what went wrong arrives at the moment they have
// already lost track of which field caused it.
//
// If a bound changes server-side, change it here too. The pairing is asserted
// nowhere, which is the honest cost of a hand-written client.

import type { Settings } from '../types'

/** schemas.py MAX_HEIGHT_CM — taller than the tallest recorded human. */
export const MAX_HEIGHT_CM = 272

/** schemas.py MAX_INPUT_GOAL_RATE_KG_PER_WEEK.
 *
 * Note this is far wider than the 1 kg/week the server *clamps* to. Anything
 * between 1 and 5 is accepted and then clamped with an explanation, because a
 * over-ambitious plan deserves an answer rather than a validation error. This
 * bound only catches input that is not a rate at all — which is nearly always
 * someone entering their goal *weight* here by mistake. */
export const MAX_GOAL_RATE_KG_PER_WEEK = 5

/** schemas.py MAX_WATER_GOAL_ML. Not a rounding: sustained intake much above
 *  10 litres a day outruns the kidneys and hyponatraemia is a real harm, so
 *  this is a goal the app declines to help anyone meet. */
export const MAX_WATER_GOAL_ML = 10000

/** schemas.py MAX_WATER_QUICK_ADD_ML — one tap should not exceed a large bottle. */
export const MAX_WATER_QUICK_ADD_ML = 2000

/** schemas.py MAX_WATER_ENTRY_ML — a hand-typed amount, which may legitimately
 *  be a jug at a restaurant. */
export const MAX_WATER_ENTRY_ML = 5000

/** schemas.py MAX_WATER_QUICK_ADDS. */
export const MAX_WATER_QUICK_ADDS = 4

/** calculations.py DEFAULT_WATER_QUICK_ADDS — what an account that has never
 *  customised them gets. The server stores NULL in that case rather than these
 *  values, so the client is what turns "unset" into buttons. */
export const DEFAULT_WATER_QUICK_ADDS = [250, 500, 750]

/** schemas.py MAX_STEPS_PER_DAY. Carries no health opinion, unlike the water
 *  ceiling above — there is no amount of walking this app declines to help
 *  anyone do. It only catches a figure that is not a step count at all. */
export const MAX_STEPS_PER_DAY = 200_000

/** calculations.py WATER_ML_PER_KG. Needed here for one message only: the
 *  card has to name the rate before any weigh-in exists for the server to
 *  report it alongside. */
export const WATER_ML_PER_KG = 35

/** schemas.py MAX_SUPPLEMENTS. Carries no opinion about what anyone takes —
 *  it bounds a tick list to something a person can actually read through
 *  every day. */
export const MAX_SUPPLEMENTS = 30

/** schemas.py MAX_SUPPLEMENT_TIMES. */
export const MAX_SUPPLEMENT_TIMES = 6

/** schemas.py MAX_SUPPLEMENT_NAME / MAX_SUPPLEMENT_DOSE. */
export const MAX_SUPPLEMENT_NAME = 100
export const MAX_SUPPLEMENT_DOSE = 60

/** Why a supplement would be refused, or null if it would not be.
 *
 * Deliberately not part of `settingsFieldRules`: a supplement is a row in its
 * own table, not a `keyof Settings`, so there is no key for that record to hang
 * a rule on. Same job as validateWaterQuickAdd, different shape. */
export function validateSupplement(
  name: string,
  dose: string,
  times: string[],
): string | null {
  if (name.trim() === '') return 'Give it a name.'
  if (name.trim().length > MAX_SUPPLEMENT_NAME) {
    return `A name has to be ${MAX_SUPPLEMENT_NAME} characters or fewer.`
  }
  if (dose.trim().length > MAX_SUPPLEMENT_DOSE) {
    return `A dose has to be ${MAX_SUPPLEMENT_DOSE} characters or fewer.`
  }
  if (times.length === 0) {
    return 'Add at least one time of day — that is what there is to tick off.'
  }
  if (times.length > MAX_SUPPLEMENT_TIMES) {
    return `Up to ${MAX_SUPPLEMENT_TIMES} times a day.`
  }
  // The server's own pattern. A <input type="time"> yields exactly this shape,
  // so this only fires for a browser that falls back to a text input.
  if (times.some((time) => !/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(time))) {
    return 'Times need to look like 08:00.'
  }
  return null
}

/** banking.py MAX_PLAN_DAYS. A plan, not a diet: spreading further than a
 *  fortnight is a change to the calorie goal itself, where the TDEE machinery
 *  can see it. */
export const MAX_PLAN_DAYS = 14

/** banking.py MAX_DAY_DELTA_KCAL. Carries no health opinion — the calorie
 *  floors do that, and they refuse rather than clamp. This one only catches a
 *  misplaced zero before it reaches the server. */
export const MAX_DAY_DELTA_KCAL = 3000

/** schemas.py MAX_PLAN_HORIZON_DAYS. Bounds how far away a plan's days are,
 *  which MAX_PLAN_DAYS does not: fourteen days scattered across a decade would
 *  satisfy that bound and mean nothing. */
export const MAX_PLAN_HORIZON_DAYS = 365

/** Why a plan would be refused before it is sent, or null if it would not be.
 *
 * Only the bounds the client can check. The calorie floors are deliberately
 * NOT mirrored here: they depend on a measured expenditure this screen does not
 * have, and a floor guessed at client-side would refuse plans the server would
 * allow — which is worse than the round trip, because the user cannot tell a
 * wrong refusal from a right one. Those come back from the server naming the
 * day and the reason. */
export function validatePlan(
  dates: string[],
  amount: number | null,
  needsAmount: boolean,
): string | null {
  if (dates.length === 0) {
    return 'Pick at least one day to absorb the change.'
  }
  if (dates.length > MAX_PLAN_DAYS) {
    return `A plan can cover at most ${MAX_PLAN_DAYS} days.`
  }
  if (!needsAmount) return null
  if (amount === null || !Number.isFinite(amount) || amount === 0) {
    return 'Say how many calories to move onto the day you are planning for.'
  }
  if (Math.abs(amount) > MAX_DAY_DELTA_KCAL) {
    return `A single day cannot move by more than ${MAX_DAY_DELTA_KCAL.toLocaleString()} kcal — check for a stray digit.`
  }
  return null
}

/** schemas.py FoodCreate.name max_length. */
export const MAX_FOOD_NAME = 200

/** Why a food would be refused, or null if it would not be.
 *
 * Same shape and same reasoning as validateSupplement above: a food is a row in
 * its own table, not a `keyof Settings`.
 *
 * Carbs and fat arrive already parsed to `number | null` rather than as
 * strings, because "not recorded" and "zero" are different claims and only the
 * caller's input handling can tell them apart -- `Number('')` is 0, which would
 * turn a blank box into a positive assertion that the food contains no carbs. */
export function validateFood(
  name: string,
  servingSize: number | null,
  calories: number | null,
  protein: number | null,
  carbs: number | null,
  fat: number | null,
): string | null {
  if (name.trim() === '') return 'Give it a name.'
  if (name.trim().length > MAX_FOOD_NAME) {
    return `A name has to be ${MAX_FOOD_NAME} characters or fewer.`
  }
  // schemas.py has serving_size gt=0: it is a divisor. LogMeal scales a food by
  // weight / serving_size, so a zero here is not merely wrong, it is the one
  // value that makes every future meal built from this food NaN.
  if (servingSize === null || !Number.isFinite(servingSize) || servingSize <= 0) {
    return 'Serving size has to be a number greater than zero — it is what the macros are per.'
  }
  const required: [string, number | null][] = [
    ['Calories', calories],
    ['Protein', protein],
  ]
  for (const [label, value] of required) {
    if (value === null || !Number.isFinite(value) || value < 0) {
      return `${label} has to be zero or more.`
    }
  }
  const optional: [string, number | null][] = [
    ['Carbs', carbs],
    ['Fat', fat],
  ]
  for (const [label, value] of optional) {
    if (value !== null && (!Number.isFinite(value) || value < 0)) {
      return `${label} has to be zero or more, or left blank.`
    }
  }
  return null
}

interface FieldRule {
  label: string
  /** Null when the value is acceptable, otherwise why it is not. */
  check: (value: number) => string | null
}

const positiveGoal = (label: string): FieldRule => ({
  label,
  check: (value) =>
    value > 0 ? null : `${label} has to be greater than zero.`,
})

export const settingsFieldRules: Partial<Record<keyof Settings, FieldRule>> = {
  water_goal_ml: {
    label: 'Water goal',
    check: (value) => {
      if (value <= 0) return 'Water goal has to be greater than zero.'
      if (value > MAX_WATER_GOAL_ML) {
        return `A daily goal above ${MAX_WATER_GOAL_ML.toLocaleString()} ml is more than the body can safely clear — this app will not set one.`
      }
      return null
    },
  },
  steps_goal: {
    label: 'Step goal',
    check: (value) => {
      if (value <= 0) return 'A step goal has to be greater than zero.'
      if (value > MAX_STEPS_PER_DAY) {
        return `A daily goal above ${MAX_STEPS_PER_DAY.toLocaleString()} steps is not a step count — check for a stray digit.`
      }
      return null
    },
  },
  calorie_goal: positiveGoal('Daily calories'),
  protein_goal: positiveGoal('Daily protein'),
  carbs_goal: positiveGoal('Daily carbs'),
  fat_goal: positiveGoal('Daily fat'),
  height_cm: {
    label: 'Height',
    check: (value) => {
      if (value <= 0) return 'Height has to be greater than zero.'
      if (value > MAX_HEIGHT_CM) {
        return `Height has to be ${MAX_HEIGHT_CM} cm or less — that is taller than anyone on record.`
      }
      return null
    },
  },
  goal_rate_kg_per_week: {
    label: 'Goal rate',
    check: (value) =>
      Math.abs(value) <= MAX_GOAL_RATE_KG_PER_WEEK
        ? null
        : `Goal rate is how fast you want your weight to change each week, not the weight you are aiming for. It has to be between −${MAX_GOAL_RATE_KG_PER_WEEK} and ${MAX_GOAL_RATE_KG_PER_WEEK} kg per week.`,
  },
}

/** Why this value would be refused, or null if it would not be.
 *
 * `null` values pass: every profile field is optional, and "not set" is always
 * a legal state. Only a value that is present and out of range is a problem. */
export function validateSettingsField(
  field: keyof Settings,
  value: number | null,
): string | null {
  if (value === null) return null
  const rule = settingsFieldRules[field]
  return rule ? rule.check(value) : null
}


/** Why a quick-add amount would be refused, or null if it would not be.
 *
 * Deliberately not part of `settingsFieldRules`: the quick-adds are elements of
 * one list field, not distinct `keyof Settings` keys, so there is no key for
 * that record to hang a rule on. Same job, different shape. */
export function validateWaterQuickAdd(value: number | null): string | null {
  if (value === null) return null
  if (!Number.isFinite(value) || value <= 0) {
    return 'A quick-add amount has to be greater than zero.'
  }
  if (value > MAX_WATER_QUICK_ADD_ML) {
    return `A single button should not add more than ${MAX_WATER_QUICK_ADD_ML.toLocaleString()} ml.`
  }
  return null
}
