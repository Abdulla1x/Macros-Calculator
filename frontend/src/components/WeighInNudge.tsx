import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { addDays, daysBetween, localIsoDate } from '../lib/dates'
import { dismissWeighInNudge, isWeighInNudgeDismissed } from '../lib/dismissals'
import { MAX_WEIGH_IN_REMINDER_DAYS } from '../lib/limits'
import { useSettings } from '../settings/SettingsContext'
import Card from './ui/Card'

/** How often the clock is re-read while waiting for the reminder time.
 *
 * The same constant and the same reasoning as SupplementsCard's: a reminder is
 * due at a minute boundary. Without this, opening the app at 19:58 with a 20:00
 * reminder shows nothing until the next focus event — which could be tomorrow,
 * so the reminder would simply not happen. Only runs while the reminder is on
 * and its time has not yet arrived. */
const CLOCK_TICK_MS = 60_000

/** "HH:MM" in the *browser's* timezone.
 *
 * Lifted from SupplementsCard for the reason stated there: the API stores no
 * timezone for anyone, so the server cannot know whether 20:00 has happened.
 * The server's date.today() is UTC, which is why "have I weighed in today" is
 * also answered here rather than by an endpoint. */
function clockTime(now: Date): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(
    now.getMinutes(),
  ).padStart(2, '0')}`
}

type Verdict =
  /** Not asked yet, or the request failed. A failed load must not masquerade
   *  as "you have never weighed yourself" — so this renders nothing. */
  | { kind: 'unknown' }
  | { kind: 'due'; lastDate: string | null }
  | { kind: 'notDue' }

/** The opt-in weigh-in nudge.
 *
 * A weigh-in is an input, not a readout: it feeds the trend, the measured daily
 * burn, and — with targets_auto on — the four daily goals. Skipped days thin
 * all three, and nothing in the app has ever said so.
 *
 * Renders in Layout below StatusBanner, so an outage notice outranks a
 * reminder, and above the outlet so it reaches someone who never navigates to
 * /weight. NOT in the dashboard tracker grid: every child of that grid follows
 * `viewedDate` by design, and that is often not today.
 *
 * Off by default and returns null outright when it is off, so an account that
 * never opts in renders not one extra element.
 */
export default function WeighInNudge() {
  const { settings } = useSettings()
  // Already where the card would send you. This also removes the only way the
  // card could go stale: it structurally cannot be on screen at the moment a
  // weigh-in is saved, so there is nothing to invalidate afterwards.
  const onWeightPage = useLocation().pathname === '/weight'

  const [today, setToday] = useState(localIsoDate)
  const [clock, setClock] = useState(() => clockTime(new Date()))
  const [dismissed, setDismissed] = useState(false)
  const [verdict, setVerdict] = useState<Verdict>({ kind: 'unknown' })

  const reminderTime = settings?.weigh_in_reminder_time ?? null
  const cadence = settings?.weigh_in_reminder_days ?? 1
  const timeArrived = reminderTime !== null && clock >= reminderTime
  const shouldAsk = timeArrived && !dismissed && !onWeightPage

  // Past midnight the date changes under us, which re-keys the dismissal and
  // makes yesterday's answer wrong. Same pair Dashboard uses to roll its
  // viewed date forward; same-value updates are no-ops.
  useEffect(() => {
    const refresh = () => {
      setToday(localIsoDate())
      setClock(clockTime(new Date()))
    }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])

  // Re-read the dismissal whenever the day changes, or a card dismissed
  // yesterday would stay hidden today.
  useEffect(() => {
    setDismissed(isWeighInNudgeDismissed(today))
  }, [today])

  useEffect(() => {
    if (reminderTime === null || timeArrived) return
    const timer = setInterval(() => setClock(clockTime(new Date())), CLOCK_TICK_MS)
    return () => clearInterval(timer)
  }, [reminderTime, timeArrived])

  useEffect(() => {
    if (!shouldAsk) return
    let cancelled = false
    setVerdict({ kind: 'unknown' })
    // A window rather than the whole log: the cadence cannot exceed
    // MAX_WEIGH_IN_REMINDER_DAYS, so one day past it is all that can change the
    // answer. Bounded at ~31 rows, against an endpoint that would otherwise
    // return up to 500.
    api
      .getWeights(addDays(today, -(MAX_WEIGH_IN_REMINDER_DAYS + 1)), today)
      .then((entries) => {
        if (cancelled) return
        // Oldest-first from the server, so the last row is the most recent.
        const last = entries[entries.length - 1]?.date ?? null
        if (last === null || daysBetween(last, today) >= cadence) {
          setVerdict({ kind: 'due', lastDate: last })
        } else {
          setVerdict({ kind: 'notDue' })
        }
      })
      .catch(() => {
        if (!cancelled) setVerdict({ kind: 'unknown' })
      })
    return () => {
      cancelled = true
    }
  }, [shouldAsk, today, cadence])

  // After every hook, so the hook order never changes. An account with the
  // reminder off adds nothing to the DOM at all — not even a live region.
  if (reminderTime === null) return null

  const showing = shouldAsk && verdict.kind === 'due'
  // The wrapper is unconditional *within* an opted-in account, for the reason
  // StatusBanner states: a live region has to be in the DOM before its content
  // arrives, or there is nothing for assistive technology to observe. The card
  // always arrives after an async fetch.
  return (
    <div role="status" aria-live="polite">
      {showing && (
        <Card
          tone="brand"
          pad="none"
          className="mb-4 flex items-start gap-3 py-2 pr-2 pl-4 text-sm"
        >
          <span className="pt-2" aria-hidden="true">
            ⚖️
          </span>
          <div className="flex-1 pt-2">
            <p>
              Time for a weigh-in.
              {/* Only when it is known. An empty window cannot tell "never
                  weighed in" from "over a month ago", and inventing either is
                  the false precision this app exists to avoid. */}
              {verdict.lastDate !== null && (
                <>
                  {' '}
                  Your last one was {daysBetween(verdict.lastDate, today)} day
                  {daysBetween(verdict.lastDate, today) === 1 ? '' : 's'} ago.
                </>
              )}
            </p>
            <Link
              to="/weight"
              className="mt-0.5 inline-block font-medium text-emerald-300 hover:text-emerald-200"
            >
              Log a weigh-in →
            </Link>
          </div>
          {/* h-11/w-11 is 44px. StatusBanner's ✕ is a bare glyph well under
              that; this one is a real target on a phone. */}
          <button
            onClick={() => {
              dismissWeighInNudge(today)
              setDismissed(true)
            }}
            aria-label="Dismiss until tomorrow"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-control text-ink-muted hover:text-ink"
          >
            ✕
          </button>
        </Card>
      )}
    </div>
  )
}
