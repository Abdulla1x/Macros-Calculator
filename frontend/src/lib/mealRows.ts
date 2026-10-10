// The by-hand form's ingredient rows: how a row is built from each thing that
// can fill the form (a logged meal, a template, an AI estimate), and how a row
// becomes calories. Moved out of the Log form so the AI result can save an
// estimate directly with exactly the same arithmetic: two copies of "how many
// calories is this meal" would be two things that can disagree.
//
// Imports carry their .ts extension, as do the modules they reach, because the
// unit tests (tests/mealRows.test.ts) compile this chain for Node, which
// resolves files by their exact names; Vite accepts either.
import type { FoodSource } from './foodSources.ts'
import { matchItem, rowFieldsFromMatch } from './libraryMatch.ts'
import { num } from './parse.ts'
import type { AnalyzedItem, Food, Meal, MealTemplate } from '../types.ts'

export interface Row {
  key: number
  name: string
  weight: string
  servingSize: string
  calories: string
  protein: string
  carbs: string
  fat: string
  fromLibrary: boolean
  saveToLibrary: boolean
  /** Whose figures these are: a table or Open Food Facts when picked from the
   *  autocomplete, else 'user'. Saved with the row if the tick is on, and
   *  reset to 'user' by any number edit (updateRow). */
  source: FoodSource
}

let rowCounter = 0
export const emptyRow = (): Row => ({
  key: ++rowCounter,
  name: '',
  weight: '',
  servingSize: '100',
  calories: '',
  protein: '',
  carbs: '',
  fat: '',
  fromLibrary: false,
  saveToLibrary: true,
  source: 'user',
})

export const rowIsValid = (row: Row) => {
  const weight = num(row.weight)
  const serving = num(row.servingSize)
  const calories = num(row.calories)
  const protein = num(row.protein)
  const carbs = num(row.carbs)
  const fat = num(row.fat)
  return (
    weight !== null && weight > 0 &&
    serving !== null && serving > 0 &&
    calories !== null && calories >= 0 &&
    protein !== null && protein >= 0 &&
    (row.carbs.trim() === '' || (carbs !== null && carbs >= 0)) &&
    (row.fat.trim() === '' || (fat !== null && fat >= 0))
  )
}

// Mirrors MAX_TEMPLATE_ITEMS in backend/app/schemas.py. Duplicated here only so
// the user gets a sentence instead of a bare 422 — the server is the authority.
export const MAX_TEMPLATE_ITEMS = 30

// Ingredients aren't persisted with a meal, so editing loads the stored totals
// as one pass-through row: weight == serving size, so factor = 1 and the
// macros come through unchanged (same trick applyAnalysis uses).
//
// Takes anything carrying a name and the four macros, which is a meal or a
// template that has no items of its own.
export const rowFromTotals = (
  source: Pick<Meal, 'name' | 'calories' | 'protein' | 'carbs' | 'fat'>,
): Row => ({
  ...emptyRow(),
  name: source.name,
  weight: '100',
  servingSize: '100',
  calories: String(source.calories),
  protein: String(source.protein),
  carbs: source.carbs == null ? '' : String(source.carbs),
  fat: source.fat == null ? '' : String(source.fat),
  saveToLibrary: false,
})

// Just the fields rowsFromTemplate actually reads, rather than a whole
// MealTemplate -- the same narrowing rowFromTotals above already uses. It is
// what lets a meal arriving in a share code, which has no id and was never a
// row in this account, be applied by the identical function.
export type Applicable = Pick<
  MealTemplate,
  'name' | 'calories' | 'protein' | 'carbs' | 'fat' | 'items'
>

// A template keeps its ingredient rows, so applying one restores each at the
// weight it was saved at — which is the entire reason templates store items
// rather than just totals: the rice stays adjustable on its own.
//
// A template saved while editing an existing meal has no items, only totals,
// and so does every code made from a logged meal. Returning zero rows there
// would open the form empty and then refuse to save, complaining about
// ingredients the user never entered.
export const rowsFromTemplate = (template: Applicable): Row[] =>
  template.items.length === 0
    ? [rowFromTotals(template)]
    : template.items.map((item) => ({
        ...emptyRow(),
        name: item.name,
        weight: String(item.weight_grams),
        servingSize: String(item.serving_size),
        calories: String(item.calories),
        protein: String(item.protein),
        carbs: item.carbs == null ? '' : String(item.carbs),
        fat: item.fat == null ? '' : String(item.fat),
        saveToLibrary: false,
      }))

// One item of an AI estimate as a row. Two shapes, and which one you get is the
// whole point of attaching a food:
//
//  * Unmatched -- the model estimated everything, so weight == serving size and
//    factor = 1 passes its per-portion numbers through untouched (the same trick
//    rowFromTotals uses).
//  * Matched -- serving size and macros are the user's own saved figures while
//    weight is the model's portion estimate, so rowTotals scales the one by the
//    other. The AI estimated the portion; the library supplied the macros.
export const rowFromAnalyzedItem = (item: AnalyzedItem, attached: Food[]): Row => {
  const matched = matchItem(item, attached)
  if (!matched) {
    return {
      ...emptyRow(),
      name: item.name,
      weight: String(item.portion_grams),
      servingSize: String(item.portion_grams),
      calories: String(item.calories),
      protein: String(item.protein),
      carbs: item.carbs == null ? '' : String(item.carbs),
      fat: item.fat == null ? '' : String(item.fat),
      saveToLibrary: false,
    }
  }
  const fields = rowFieldsFromMatch(item, matched)
  return {
    ...emptyRow(),
    name: fields.name,
    weight: String(fields.weight),
    servingSize: String(fields.servingSize),
    calories: String(fields.calories),
    protein: String(fields.protein),
    carbs: fields.carbs === null ? '' : String(fields.carbs),
    fat: fields.fat === null ? '' : String(fields.fat),
    // The row really did come from the library, so the badge it lights is true
    // and the offer-to-cache tick correctly stays away: it is already saved.
    fromLibrary: true,
    saveToLibrary: false,
  }
}

export const rowTotals = (row: Row) => {
  const factor = Number(row.weight) / Number(row.servingSize)
  const scale = (value: string) => {
    const parsed = num(value)
    return parsed === null ? null : parsed * factor
  }
  return {
    calories: (num(row.calories) ?? 0) * factor,
    protein: (num(row.protein) ?? 0) * factor,
    carbs: scale(row.carbs),
    fat: scale(row.fat),
  }
}

/** The meal's totals: the valid rows summed. Carbs and fat stay null unless at
 *  least one row states them, so "not tracked" is not saved as 0 g. */
export function mealTotals(rows: Row[]) {
  return rows.filter(rowIsValid).reduce(
    (acc, row) => {
      const t = rowTotals(row)
      return {
        calories: acc.calories + t.calories,
        protein: acc.protein + t.protein,
        carbs: t.carbs === null ? acc.carbs : (acc.carbs ?? 0) + t.carbs,
        fat: t.fat === null ? acc.fat : (acc.fat ?? 0) + t.fat,
      }
    },
    { calories: 0, protein: 0, carbs: null as number | null, fat: null as number | null },
  )
}
