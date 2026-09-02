import type { AnalyzedItem, Food, FoodCreate } from '../types'

/**
 * Matching an AI item to one of the user's saved foods, and the conversion that
 * moving numbers between them needs.
 *
 * Two conventions meet here and they are not the same one. An AnalyzedItem's
 * macros are for the portion the model estimated; a Food's are per its
 * `serving_size` grams; and a LogMeal row holds per-serving figures that
 * rowTotals scales by `weight / servingSize` when it renders. A number carried
 * from one convention to another without conversion is wrong by the portion
 * ratio -- silently, and by a factor that still looks plausible on screen.
 *
 * This lives in lib/ rather than in either component because both need the same
 * answer: MealAnalyzer displays the matched numbers and LogMeal turns them into
 * rows, and the card disagreeing with the rows below it about one ingredient is
 * the quiet inconsistency the feature exists to remove. oxlint's
 * react/only-export-components would also refuse these as exports beside a
 * component.
 */

/** What the analyzer knew about the library when an estimate was applied.
 *
 * Two arrays because the two halves are not the same question. A match against
 * `attached` is applied outright: the user picked that food and the model was
 * handed its numbers as facts. A match against the rest of `library` is only
 * ever *offered*, because nobody claimed that food is on the plate -- the names
 * merely coincide, and swapping numbers on that basis is the app deciding for
 * the user. */
export interface LibraryContext {
  attached: Food[]
  library: Food[]
}

const sameName = (a: string, b: string) =>
  a.trim().toLowerCase() === b.trim().toLowerCase()

/**
 * The saved food this item is, or null.
 *
 * `matched_food_name` first: that is the model answering the question it was
 * asked. `item.name` second, for the case where it used an attached food's
 * numbers and simply did not say so -- the prompt rule is new, and a model is
 * free to ignore it. A `matched_food_name` matching nothing in `foods` is
 * discarded rather than trusted: a name the model invented must never move a
 * number.
 *
 * A non-positive portion counts as no match. AnalyzedItem deliberately carries
 * no numeric bounds -- Gemini rejects them in a structured-output schema -- so
 * zero is expressible, and it is the divisor in rowFieldsFromMatch below.
 */
export function matchItem(item: AnalyzedItem, foods: Food[]): Food | null {
  if (!(item.portion_grams > 0)) return null
  const claimed = item.matched_food_name
  return (claimed ? findByName(claimed, foods) : null) ?? findByName(item.name, foods)
}

/** The saved food with this exact name, or null.
 *
 * Case- and whitespace-insensitive, and the single definition of "the same
 * food" in the app -- LogMeal offers a swap on the strength of this comparison,
 * so it must be the one matchItem uses rather than a second spelling of it. */
export function findByName(name: string, foods: Food[]): Food | null {
  return foods.find((food) => sameName(food.name, name)) ?? null
}

/**
 * The library's macros scaled to the portion the model estimated.
 *
 * What MealAnalyzer prints for a matched item, so the estimate card and the row
 * the apply button produces show the same figures.
 */
export function perPortion(item: AnalyzedItem, food: Food) {
  const factor = item.portion_grams / food.serving_size
  return { calories: food.calories * factor, protein: food.protein * factor }
}

/**
 * Row fields for a matched item: the model's portion, the library's macros.
 *
 * The division of labour, written out. `weight` is the model's estimate of how
 * much was eaten; `servingSize` and the macros are the user's own recorded
 * facts; and LogMeal's existing rowTotals multiplies one by the other. No new
 * arithmetic -- except for a macro the library does not hold.
 *
 * carbs and fat are nullable on a foods row. Where one is missing the model's
 * own estimate is kept, but it must be converted first: that figure is for the
 * portion while this field is per serving, so handing it over untouched would
 * let rowTotals scale it a second time.
 *
 * Call this only with a food that came from matchItem, which is what guarantees
 * `portion_grams` is positive and the division below is safe.
 */
export function rowFieldsFromMatch(item: AnalyzedItem, food: Food) {
  const perServing = food.serving_size / item.portion_grams
  const fill = (fromFood: number | null, fromItem: number | null) => {
    if (fromFood !== null) return fromFood
    return fromItem === null ? null : fromItem * perServing
  }
  return {
    name: food.name,
    weight: item.portion_grams,
    servingSize: food.serving_size,
    calories: food.calories,
    protein: food.protein,
    carbs: fill(food.carbs, item.carbs),
    fat: fill(food.fat, item.fat),
  }
}

/**
 * An AI-estimated item as a library food, per `servingSize` grams.
 *
 * The third direction this module converts in, and the only one whose result
 * outlives the meal. An AnalyzedItem's macros are for the portion the model
 * estimated -- 141 kcal of dip because it judged 47 g were on the plate -- while
 * a Food's are per its own serving size. Storing the portion *as* the serving is
 * arithmetically correct and practically useless: it leaves a library row reading
 * "141 kcal / 47 g", a serving nobody will ever weigh again. 100 g is what the
 * library already defaults to and what Open Food Facts reports against, so that
 * is what a saved estimate becomes.
 *
 * Rounded to one decimal because the only caller is a form the user is about to
 * read. Handing an input `300.00000000000006` invites them to "fix" a number that
 * was never wrong, and one decimal is already finer than the estimate it came
 * from.
 *
 * carbs and fat stay null when the model returned null. On a foods row null means
 * "not recorded", which is not zero -- see lib/limits.ts and lib/parse.ts.
 *
 * `source` is 'user'. foods.source is CHECK-constrained to 'user' or
 * 'openfoodfacts', so there is no honest third badge to set without a migration,
 * and 'openfoodfacts' would be a lie. What makes 'user' true is the form: these
 * numbers are shown for review and become the user's on save.
 *
 * Call this only for an item with a positive `portion_grams`. It is the divisor,
 * and AnalyzedItem carries no numeric bounds at all -- Gemini rejects them in a
 * structured-output schema, which backend/app/schemas.py explains at length -- so
 * zero and negatives are expressible. matchItem makes the same check above, for
 * the same reason.
 */
export function foodFromAnalyzedItem(item: AnalyzedItem, servingSize = 100): FoodCreate {
  const factor = servingSize / item.portion_grams
  const round = (value: number) => Math.round(value * factor * 10) / 10
  return {
    name: item.name,
    serving_size: servingSize,
    calories: round(item.calories),
    protein: round(item.protein),
    carbs: item.carbs === null ? null : round(item.carbs),
    fat: item.fat === null ? null : round(item.fat),
    source: 'user',
  }
}
