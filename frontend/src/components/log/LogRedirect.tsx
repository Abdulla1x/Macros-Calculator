import { Navigate, useLocation } from 'react-router-dom'
import { withLog } from './logPanelUrl'
import type { LogState } from './useLogPanel'

/** /log was a page until the Log panel replaced it. An installed app, a
 *  bookmark or anything else still pointing there lands on Today with the
 *  panel open instead, on the by-hand form when it was sent a meal to fill
 *  in, and with any `?date=` carried over. Replaces the history entry, so Back
 *  does not bounce through /log. */
export default function LogRedirect() {
  const { search, state } = useLocation()
  const sent = state as LogState | null
  const hand = Boolean(sent && (sent.editMeal || sent.template || sent.copyMeal || sent.sharedMeal))
  const date = new URLSearchParams(search).get('date')
  return <Navigate replace to={{ pathname: '/', search: withLog('', hand ? 'hand' : 'start', date) }} state={sent} />
}
