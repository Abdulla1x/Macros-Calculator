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
