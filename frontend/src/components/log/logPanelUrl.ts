/** The Log panel lives in the address, not in component state.
 *
 *  Log is an action, not a place (overhaul 0a), so it opens OVER whatever page
 *  you are on instead of replacing it. The panel is still in the address, as a
 *  `log` search parameter, for three reasons:
 *
 *  - The phone's back button closes it. Opening pushes a history entry, so
 *    Back pops it, which is what every Android user expects of a sheet.
 *  - "Enter it by hand" is a second entry on top, so Back walks hand -> start
 *    -> closed.
 *  - A reload keeps it open, and old links to /log still land somewhere (App
 *    redirects them here).
 *
 *    ?log          the start screen: the day, AI, saved and recent meals
 *    ?log=hand     the form for entering a meal by hand (and for editing one)
 *    &date=YYYY-MM-DD   the day the meal is for; absent means today
 *
 *  Router state carries what a URL cannot: the meal being edited, a template, a
 *  copied meal, a pasted code. Plus `logDepth`, how many history entries the
 *  panel has pushed, so closing it can step back over all of them at once and
 *  a save does not leave Back reopening the form. */
export type LogScreen = 'start' | 'hand'

const PARAM = 'log'
const DATE = 'date'

export function logScreen(search: string): LogScreen | null {
  const params = new URLSearchParams(search)
  if (!params.has(PARAM)) return null
  return params.get(PARAM) === 'hand' ? 'hand' : 'start'
}

export function logDate(search: string): string | null {
  return new URLSearchParams(search).get(DATE)
}

/** The search string with the panel open on `screen`. Other parameters the
 *  page underneath uses are kept. `date` undefined keeps the current one; null
 *  removes it. */
export function withLog(search: string, screen: LogScreen, date?: string | null): string {
  const params = new URLSearchParams(search)
  params.set(PARAM, screen === 'hand' ? 'hand' : '')
  if (date === null) params.delete(DATE)
  else if (date !== undefined) params.set(DATE, date)
  return tidy(params)
}

/** The search string with the panel and its date removed. */
export function withoutLog(search: string): string {
  const params = new URLSearchParams(search)
  params.delete(PARAM)
  params.delete(DATE)
  return tidy(params)
}

// URLSearchParams writes an empty value as "log=", which reads like a bug in
// the address bar; the bare flag is what the comments above promise.
function tidy(params: URLSearchParams): string {
  const text = params.toString().replace(/(^|&)log=(?=&|$)/, '$1log')
  return text ? `?${text}` : ''
}

/** How many entries the panel pushed onto the history, read from router state.
 *  Zero when it was opened by a reload or a redirect, where there is nothing
 *  of ours to step back over. */
export function logDepth(state: unknown): number {
  const depth = (state as { logDepth?: unknown } | null)?.logDepth
  return typeof depth === 'number' && depth > 0 ? depth : 0
}
