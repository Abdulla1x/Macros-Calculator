/** What the Log button says while an AI estimate is in the background
 *  (overhaul 0a, DESIGN.md Buttons -> Log button).
 *
 *    idle     nothing running, or the answer has been seen
 *    working  an estimate is on its way: a spinner where the plus was
 *    ready    it arrived while no screen showed it: a dot and "Ready"
 *
 *  The tab bar's middle slot only fits a short label ("Estimating…" covered
 *  the Progress tab at 328px in the 0a wireframe), so it keeps "Log" while
 *  working; the rail has room to say more. The full state is always in the
 *  accessible name, so a screen reader hears it at either width, and that name
 *  contains the visible words (WCAG 2.5.3, label in name), so "Ready" works as
 *  a voice command. */
export type LogButtonState = 'idle' | 'working' | 'ready'

export function logButtonState(analyzing: boolean, unseen: boolean): LogButtonState {
  if (analyzing) return 'working'
  return unseen ? 'ready' : 'idle'
}

const LABELS: Record<'bar' | 'rail', Record<LogButtonState, string>> = {
  bar: { idle: 'Log', working: 'Log', ready: 'Ready' },
  rail: { idle: 'Log a meal', working: 'Estimating…', ready: 'Estimate ready' },
}

const SPOKEN: Record<LogButtonState, string> = {
  idle: 'Log a meal',
  working: 'Log a meal, estimating',
  ready: 'Log a meal, estimate ready',
}

export function logButtonLabel(place: 'bar' | 'rail', state: LogButtonState) {
  return { visible: LABELS[place][state], spoken: SPOKEN[state] }
}
