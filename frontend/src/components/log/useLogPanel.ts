import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { logDepth, logScreen, withLog, withoutLog, type LogScreen } from './logPanelUrl'

/** What a screen can hand the by-hand form through router state. */
export type LogState = {
  editMeal?: unknown
  template?: unknown
  copyMeal?: unknown
  sharedMeal?: unknown
  sharedCode?: string
  /** The estimate in AnalysisProvider should fill the form. */
  fromEstimate?: boolean
}

/** Open, move within and close the Log panel (see logPanelUrl.ts for why it
 *  lives in the address). Every caller goes through this, so the history
 *  bookkeeping is in one place. */
export function useLogPanel() {
  const location = useLocation()
  const navigate = useNavigate()
  const screen = logScreen(location.search)
  const depth = logDepth(location.state)

  /** Open the panel over the current page, or move to another screen of it.
   *  Always a new history entry, so Back undoes exactly this step. */
  const open = useCallback(
    (target: LogScreen = 'start', options: { date?: string | null; state?: LogState } = {}) => {
      navigate(
        { pathname: location.pathname, search: withLog(location.search, target, options.date) },
        {
          state: {
            ...options.state,
            logDepth: (screen ? depth : 0) + 1,
            // Whether this screen was reached from the start screen, so the
            // by-hand form offers Back only when there is somewhere to go back to.
            logFromStart: screen === 'start',
          },
        },
      )
    },
    [navigate, location.pathname, location.search, screen, depth],
  )

  /** Change the day without adding a history entry: picking "Yesterday" is not
   *  a step anyone wants Back to undo. */
  const setDate = useCallback(
    (date: string | null) => {
      if (!screen) return
      navigate(
        { pathname: location.pathname, search: withLog(location.search, screen, date) },
        { replace: true, state: location.state },
      )
    },
    [navigate, location.pathname, location.search, location.state, screen],
  )

  /** Close the whole panel. Steps back over every entry it pushed, so after a
   *  save Back does not reopen the form; a panel opened by a reload or a
   *  redirect pushed nothing, so its flag is simply removed. */
  const close = useCallback(() => {
    if (depth > 0) navigate(-depth)
    else navigate({ pathname: location.pathname, search: withoutLog(location.search) }, { replace: true })
  }, [navigate, depth, location.pathname, location.search])

  /** From the by-hand form back to the start screen. */
  const back = useCallback(() => {
    if (depth > 1) navigate(-1)
    else navigate({ pathname: location.pathname, search: withLog(location.search, 'start') }, { replace: true })
  }, [navigate, depth, location.pathname, location.search])

  return { screen, open, setDate, close, back }
}
