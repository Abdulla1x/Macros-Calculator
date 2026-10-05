/** What one AI analysis request was built from.
 *
 * Kept free of the DOM -- the photos are compared by identity, never read -- so
 * the rule below runs under `npm test`. MealAnalyzer records one of these for
 * every estimate it receives, and asks `sameInputs` before sending another.
 */
export interface AnalysisInputs<Photo> {
  note: string
  photos: readonly Photo[]
  foodIds: readonly number[]
}

/** Whether a new request would send exactly what produced the estimate on screen.
 *
 * Measured in the 2026-10-05 AI audit: a run with nothing changed spends one of
 * the day's AI calls (the free tier is 20 a day per model for the whole app) and
 * moves the answer by a median of ~3%, which is the model's own run-to-run noise.
 * That is the only case this catches. A note edited by a single character, a
 * photo added, removed or reordered, or a saved food attached or removed all
 * count as a change, because each is new information the model has not seen.
 *
 * - The note is compared trimmed, because the request sends it trimmed.
 * - Photos are compared by identity and in order: the prompt treats the order
 *   as meaningful ("the first photo"), and the same picture picked twice is a
 *   new File, which is the honest answer, since it is a new upload.
 * - Saved foods are compared as a set, since attaching in a different order
 *   tells the model nothing new.
 */
export function sameInputs<Photo>(
  a: AnalysisInputs<Photo>,
  b: AnalysisInputs<Photo>,
): boolean {
  if (a.note.trim() !== b.note.trim()) return false
  if (a.photos.length !== b.photos.length) return false
  if (a.photos.some((photo, index) => photo !== b.photos[index])) return false
  const foods = new Set(a.foodIds)
  return foods.size === new Set(b.foodIds).size && b.foodIds.every((id) => foods.has(id))
}
