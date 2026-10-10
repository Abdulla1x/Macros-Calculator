// "The meals changed": a save in the Log panel, told to whatever page is
// underneath it.
//
// The panel opens over the page you were on instead of replacing it, so that
// page never remounts and never refetches. Today would keep showing the day
// without the meal just saved. A window event rather than a shared store:
// meals are fetched per page, by date, and each page knows best what to
// reload; this only says when.

const EVENT = 'trackaholic:meals-changed'

/** What changed: the day the saved meal is on, so a page showing that day can
 *  bring it into view, and a page showing another day only refreshes. */
export interface MealsChange {
  date: string
}

export function announceMealsChanged(change: MealsChange) {
  window.dispatchEvent(new CustomEvent<MealsChange>(EVENT, { detail: change }))
}

/** Returns the cleanup, so it drops straight into a useEffect. */
export function onMealsChanged(listener: (change: MealsChange) => void): () => void {
  const handle = (event: Event) => listener((event as CustomEvent<MealsChange>).detail)
  window.addEventListener(EVENT, handle)
  return () => window.removeEventListener(EVENT, handle)
}
