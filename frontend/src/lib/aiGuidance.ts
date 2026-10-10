// Teaching the AI box to be used well (UA-25, owner 2026-10-10: a nudge at the
// moment of a photo-only estimate, plus one dismissible tip card).
//
// Why it is worth a screen element at all, measured on the model evaluation:
// a photo alone reads about two thirds low on calorie-dense meals on every
// model tried, because oil, butter and sauces barely show; with a note the
// error is ~4-6%. Asking is the cheapest accuracy there is.

/** What a photo hides most often, as the chips the question offers. */
export const HIDDEN_EXTRAS = ['Oil', 'Butter', 'Sauce', 'Sugar or honey', 'Nut butter'] as const

/** Ask about hidden extras only when photos are the whole story: with any
 *  note at all, the user has already said what they want to say, and a
 *  question then would be a nag. */
export function shouldAskAboutHidden(photos: number, note: string): boolean {
  return photos > 0 && note.trim() === ''
}

/** The note with the picked extras added as one plain line the model reads,
 *  "Also in it: oil and sauce.", kept in the box so the user sees exactly
 *  what was sent and can add amounts next time. */
export function noteWithExtras(note: string, picks: readonly string[]): string {
  if (picks.length === 0) return note
  const names = picks.map((pick) => pick.toLowerCase())
  const list = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0]
  const line = `Also in it: ${list}.`
  return note.trim() ? `${note.trim()}\n${line}` : line
}
