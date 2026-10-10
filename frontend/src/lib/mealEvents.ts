// "The meals changed": a save in the Log panel, told to whatever page is
// underneath it.
//
// The panel opens over the page you were on instead of replacing it, so that
// page never remounts and never refetches. Today would keep showing the day
// without the meal just saved. A window event rather than a shared store:
// meals are fetched per page, by date, and each page knows best what to
// reload; this only says when.

const EVENT = 'trackaholic:meals-changed'

export function announceMealsChanged() {
  window.dispatchEvent(new Event(EVENT))
}

/** Returns the cleanup, so it drops straight into a useEffect. */
export function onMealsChanged(listener: () => void): () => void {
  window.addEventListener(EVENT, listener)
  return () => window.removeEventListener(EVENT, listener)
}
