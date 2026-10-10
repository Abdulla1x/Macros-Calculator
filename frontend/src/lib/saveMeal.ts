// Saving a meal, and saving one as a template, from ingredient rows.
//
// Shared by the by-hand form and the AI result's "Save meal", which saves an
// estimate without opening the form. Both must write exactly the same meal for
// the same rows, link the same estimate, and round the same way, so there is
// one routine rather than two that could drift.
import { api } from '../api/client'
import { mealTotals, rowIsValid, type Row } from './mealRows'
import { num } from './parse'
import type { Meal } from '../types'

const hundredths = (value: number) => Math.round(value * 100) / 100

/** Create the meal (or update `editId`), link the AI estimate it came from,
 *  and save any rows ticked for the library. Throws if the meal itself fails;
 *  the two follow-ups are best-effort and never do. */
export async function saveMeal({
  rows,
  name,
  date,
  editId = null,
  analysisId = null,
}: {
  rows: Row[]
  name: string
  date: string
  editId?: number | null
  analysisId?: number | null
}): Promise<Meal> {
  const totals = mealTotals(rows)
  const payload = {
    date,
    name: name.trim(),
    calories: hundredths(totals.calories),
    protein: hundredths(totals.protein),
    carbs: totals.carbs === null ? null : hundredths(totals.carbs),
    fat: totals.fat === null ? null : hundredths(totals.fat),
  }
  const meal = editId !== null ? await api.updateMeal(editId, payload) : await api.createMeal(payload)

  // Best-effort: remember which AI analysis this meal came from.
  if (analysisId !== null) await api.linkAnalysis(analysisId, meal.id).catch(() => null)

  // Offer-to-cache: persist manually entered ingredients the user opted in on.
  // Best-effort -- the meal is already saved, and a failed library write must
  // not surface as "Saving failed" (which would invite a duplicate re-save).
  await Promise.all(
    rows
      .filter(rowIsValid)
      .filter((row) => !row.fromLibrary && row.saveToLibrary && row.name.trim())
      .map((row) =>
        api
          .saveFood({
            name: row.name.trim(),
            serving_size: Number(row.servingSize),
            calories: Number(row.calories),
            protein: Number(row.protein),
            carbs: num(row.carbs),
            fat: num(row.fat),
            source: row.source,
          })
          .catch(() => null),
      ),
  )
  return meal
}

/** Save the rows as a template under `name`. Resolves to whether it was new
 *  or replaced one of the same name, because replacing throws away an
 *  ingredient list and the caller should say so. */
export async function saveTemplate(rows: Row[], name: string): Promise<{ created: boolean }> {
  const valid = rows.filter(rowIsValid)
  const totals = mealTotals(rows)
  return api.saveMealTemplate({
    name,
    calories: hundredths(totals.calories),
    protein: hundredths(totals.protein),
    carbs: totals.carbs === null ? null : hundredths(totals.carbs),
    fat: totals.fat === null ? null : hundredths(totals.fat),
    items: valid.map((row) => ({
      // A row is valid without a name, but the API requires one on every
      // item -- so an unnamed ingredient gets a placeholder rather than a 422
      // the user has no way to interpret.
      name: row.name.trim() || 'Ingredient',
      weight_grams: Number(row.weight),
      serving_size: Number(row.servingSize),
      calories: Number(row.calories),
      protein: Number(row.protein),
      carbs: num(row.carbs),
      fat: num(row.fat),
    })),
  })
}
