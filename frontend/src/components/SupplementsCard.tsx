import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { localIsoDate } from '../lib/dates'
import { trackerHues } from '../lib/chartTheme'
import type { SupplementDay, SupplementSlot } from '../types'
import DailyTrackerCard from './DailyTrackerCard'

interface Props {
  /** The day being viewed on the dashboard, not necessarily today. */
  date: string
}

/** How often the clock is re-read while the card is on screen.
 *
 * A dose is due at a minute boundary, so anything finer is wasted renders and
 * anything coarser leaves "overdue" up to a minute late — which is exactly the
 * kind of small lie the caption exists to avoid. Only runs when the card is
 * showing today; a past day has no clock to compare against. */
const CLOCK_TICK_MS = 60_000

/** "HH:MM" in the *browser's* timezone.
 *
 * The whole reason due/overdue is computed here rather than on the server: the
 * API stores no timezone for anyone, so it cannot know whether 20:00 has
 * happened. Every other derived number in this app is resolved server-side
 * because the server owns the arithmetic — it does not own this clock. */
function clockTime(now: Date): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(
    now.getMinutes(),
  ).padStart(2, '0')}`
}

export default function SupplementsCard({ date }: Props) {
  const [day, setDay] = useState<SupplementDay | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => new Date())
  // Which toggle is the most recent. Ticking several boxes quickly puts two
  // requests in flight, and each response carries the *whole* day as the server
  // saw it — so an older one landing last would undo the newer change on screen
  // and stay wrong until a reload. Only the latest response is applied.
  const latestToggle = useRef(0)

  const isToday = date === localIsoDate()

  const load = useCallback(() => {
    api
      .getSupplementDay(date)
      .then((next) => {
        setDay(next)
        setError(null)
      })
      // A failed load must not render as a day with nothing scheduled — the
      // rule the water, steps and meal cards all follow. Here it matters more
      // than usual, because "nothing scheduled" is what hides this card
      // entirely, so a swallowed error would look like the feature vanishing.
      .catch(() => setError("Couldn't load your supplements for this day."))
  }, [date])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!isToday) return
    const timer = setInterval(() => setNow(new Date()), CLOCK_TICK_MS)
    return () => clearInterval(timer)
  }, [isToday])

  const toggle = async (slot: SupplementSlot) => {
    const wanted = !slot.taken
    const mine = ++latestToggle.current

    // Tick the box under the finger rather than a round-trip later. Without
    // this the checkbox is drawn purely from server state, so a tap appears to
    // do nothing at all until the response lands — which on a sleeping
    // free-tier instance is seconds, on the one card in the app you tap
    // several boxes on in a row.
    setDay((current) =>
      current === null
        ? current
        : {
            ...current,
            taken: current.taken + (wanted ? 1 : -1),
            slots: current.slots.map((other) =>
              other.supplement_id === slot.supplement_id && other.time === slot.time
                ? { ...other, taken: wanted }
                : other,
            ),
          },
    )

    try {
      // The response *is* the new day, so there is no second request here. It
      // also corrects the guess above: un-ticking the last dose in an
      // off-schedule slot removes that slot entirely, which the optimistic
      // update cannot know and the server's answer settles.
      const next = wanted
        ? await api.takeDose(slot.supplement_id, date, slot.time)
        : await api.untakeDose(slot.supplement_id, date, slot.time)
      if (latestToggle.current !== mine) return
      setDay(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
      // The optimistic tick was a guess and the guess was wrong, so go and ask.
      // Leaving it would show a dose as taken that the server never recorded.
      load()
    }
  }

  if (error && !day) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="font-semibold">
          <span className="mr-2">💊</span>Supplements
        </h2>
        <p className="mt-3 text-xs text-ink-faint">{error}</p>
      </div>
    )
  }

  // Nothing scheduled and nothing ticked: no card at all. The entry point is
  // Settings, and a permanent "add some supplements" card would spend prime
  // dashboard space explaining a feature once — the same argument that keeps
  // the Quick log panel hidden until a template exists. Distinct from the
  // error branch above, which is why that one comes first.
  if (!day || day.slots.length === 0) return null

  const nowHm = clockTime(now)
  // Lexicographic comparison is chronological for zero-padded 24-hour times,
  // which is half the reason the schedule is stored as "HH:MM" strings.
  const overdue = isToday
    ? day.slots.filter((slot) => !slot.taken && slot.time <= nowHm)
    : []
  const next = isToday
    ? day.slots.find((slot) => !slot.taken && slot.time > nowHm)
    : undefined

  return (
    <DailyTrackerCard
      icon="💊"
      label="Supplements"
      value={day.taken}
      goal={day.scheduled}
      unit="doses"
      color={trackerHues.supplements}
      error={error}
      caption={<DoseCaption day={day} isToday={isToday} overdue={overdue.length} next={next} />}
      actions={
        <ul className="space-y-1">
          {day.slots.map((slot) => {
            const key = `${slot.supplement_id}-${slot.time}`
            const isOverdue = overdue.includes(slot)
            return (
              <li key={key}>
                <label className="flex cursor-pointer items-center gap-2 rounded-lg px-1 py-1 text-sm hover:bg-slate-800">
                  <input
                    type="checkbox"
                    checked={slot.taken}
                    onChange={() => toggle(slot)}
                    className="h-4 w-4 shrink-0 accent-amber-400"
                  />
                  <span className="shrink-0 tabular-nums text-xs text-ink-faint">
                    {slot.time}
                  </span>
                  <span
                    className={`truncate ${
                      slot.taken ? 'text-ink-faint line-through' : 'text-slate-200'
                    }`}
                  >
                    {slot.name}
                    {slot.dose && (
                      <span className="ml-1.5 text-xs text-ink-faint">{slot.dose}</span>
                    )}
                  </span>
                  {isOverdue && (
                    <span className="ml-auto shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">
                      due
                    </span>
                  )}
                  {/* Marked rather than hidden: this dose was ticked on a day
                      it was scheduled, and the schedule has since moved. It is
                      history, and dropping it would turn a day that was fully
                      taken into one with a miss in it. */}
                  {slot.off_schedule && !isOverdue && (
                    <span
                      className="ml-auto shrink-0 text-xs text-ink-faint"
                      title="Not on your current schedule — shown because you ticked it on this day"
                    >
                      was scheduled
                    </span>
                  )}
                </label>
              </li>
            )
          })}
        </ul>
      }
    />
  )
}

/** What is outstanding, and — for a past day — why an unfamiliar row is there.
 *
 * Nothing here promises a notification. The card can only speak while the app
 * is open, and the Settings section says so at length rather than this caption
 * repeating it every single day.
 */
function DoseCaption({
  day,
  isToday,
  overdue,
  next,
}: {
  day: SupplementDay
  isToday: boolean
  overdue: number
  next: SupplementSlot | undefined
}) {
  if (!isToday) {
    if (day.slots.some((slot) => slot.off_schedule)) {
      return (
        <>
          One of these is no longer on your schedule. It is shown because you
          ticked it on this day, and that is what happened.
        </>
      )
    }
    return null
  }
  if (overdue > 0) {
    return (
      <>
        <span className="text-amber-300">
          {overdue} {overdue === 1 ? 'dose' : 'doses'} overdue
        </span>
        {next && <> · next at {next.time}</>}
      </>
    )
  }
  if (day.taken >= day.scheduled) return <>All done for today.</>
  return <>{next ? <>Next at {next.time}.</> : <>Nothing outstanding right now.</>}</>
}
