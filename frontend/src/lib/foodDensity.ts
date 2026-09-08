import type { Food } from '../types'

/**
 * Saved foods in the one unit that makes two of them comparable.
 *
 * Every library row stores its macros against its own serving size, which is
 * right -- it is what the packet says -- and useless for comparison. 108 kcal
 * per 90 g and 70 kcal per 50 g are the same food twice, and nothing about
 * those two lines says so until both are put over 100 g: 120 against 140.
 *
 * Display only. Nothing here writes; `api.normalizeFood` is what changes a
 * stored row, and it does the same arithmetic server-side so the number the
 * user was shown is the number they get.
 */

/** The serving size the library normalises to.
 *
 * Mirrors NORMALIZED_SERVING_G in backend/app/routers/foods.py, the same way
 * lib/limits.ts mirrors the bounds in schemas.py -- and with the same honest
 * cost: nothing asserts the pairing. It is also what the add form defaults to
 * and what foodFromAnalyzedItem converts a saved AI estimate to.
 */
export const NORMALIZED_SERVING_G = 100

/** Whether this row's macros are already per 100 g.
 *
 * What decides if the "Per 100 g" button is offered at all, and the reason the
 * server answers a normalise on such a row with an unchanged 200 rather than an
 * error: the two ends agree that there is simply nothing to do.
 */
export const isPer100g = (food: Food) => food.serving_size === NORMALIZED_SERVING_G

/** This food's calories and protein per 100 g.
 *
 * carbs and fat are left out on purpose. The panel and the row caption exist to
 * let two foods be told apart at a glance, and four figures each is not a
 * glance -- these are the two the app tracks for everyone, while carbs and fat
 * are opt-in and nullable.
 */
export function per100g(food: Food) {
  const factor = NORMALIZED_SERVING_G / food.serving_size
  return {
    calories: food.calories * factor,
    protein: food.protein * factor,
  }
}

/** "120 kcal · 13 g protein / 100 g".
 *
 * Rounded for reading, not for storage: calories to whole numbers and protein
 * to one decimal, which is what the rest of the app already shows for each.
 */
export function per100gSummary(food: Food) {
  const { calories, protein } = per100g(food)
  return `${Math.round(calories)} kcal · ${Math.round(protein * 10) / 10} g protein / ${NORMALIZED_SERVING_G} g`
}
