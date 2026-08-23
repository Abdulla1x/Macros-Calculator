// The half-written meal description, kept across a navigation.
//
// MealAnalyzer's note is the one piece of its state worth surviving a trip to
// another page. Everything else it holds is either cheap to redo (re-picking a
// photo) or actively wrong to keep (an estimate for a meal you already saved),
// but a description someone has typed or dictated is work, and losing it to a
// mistaken tap on the nav is the kind of small betrayal that stops people
// trusting a text box.
//
// sessionStorage rather than localStorage: this is a draft, not a preference.
// It should outlive a route change and die with the tab, which is exactly what
// sessionStorage means. Wrapped in try/catch for the same reason
// lib/dismissals.ts is — a browser with site data blocked throws on access, and
// a draft failing to save must never take a page down with it.

const NOTE_KEY = 'macros_meal_note_draft'

export function readNoteDraft(): string {
  try {
    return sessionStorage.getItem(NOTE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function writeNoteDraft(value: string) {
  try {
    if (value) sessionStorage.setItem(NOTE_KEY, value)
    else sessionStorage.removeItem(NOTE_KEY)
  } catch {
    /* The draft just won't survive the navigation. */
  }
}

export function clearNoteDraft() {
  writeNoteDraft('')
}
