import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { addDays, dayRange, localIsoDate, parseIsoDate } from '../../lib/dates'
import { MAX_PLAN_DAYS, MAX_PLAN_HORIZON_DAYS, validatePlan } from '../../lib/limits'
import { num } from '../../lib/parse'
import type { CaloriePlan, DaySurplus, PlanKind } from '../../types'
import Card from '../ui/Card'

/** Move calories between days without moving the week.
 *
 * One of the sections of the Settings page. They live in this folder rather
 * than in Settings.tsx itself, which otherwise carries every one of them at
 * once. This one has two modes, a day picker and a list of existing plans.
 *
 * **This screen never offers.** Nothing here appears because you went over --
 * no prompt, no "shall we cut the next four days?". You come looking for it.
 * An app that asks every time you overshoot is not a tool for planning around a
 * dinner, it is a mechanism for turning one into a debt, and the difference is
 * entirely in who starts the conversation.
 *
 * The other half of that: you choose which days absorb the change. The server
 * never picks them. All it does is refuse a set that would drop a day below the
 * calorie floor, and say which day and why.
 */

const short = (iso: string) =>
  parseIsoDate(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })

const signed = (kcal: number) =>
  `${kcal > 0 ? '+' : '−'}${Math.abs(Math.round(kcal)).toLocaleString()}`

// Server refusals name the offending day, and the server only knows a date as
// an ISO string. Every other date on this screen reads "Wed, Aug 26", so an
// unconverted 2026-08-26 in the one message that matters most leaves the user
// matching a number against the buttons above it.
//
// A narrow transform rather than a parse: YYYY-MM-DD is the only token of that
// shape these sentences contain, and anything that does not match is left
// exactly as the server wrote it.
const humaniseDates = (message: string) =>
  message.replace(/\d{4}-\d{2}-\d{2}/g, (iso) => short(iso))

export default function CaloriePlanSection({
  onRejected,
  initialDate,
}: {
  onRejected: (message: string) => void
  /** Prefills the day being planned around, when arriving from the dashboard
   *  link rather than from the settings page itself. */
  initialDate?: string
}) {
  const [plans, setPlans] = useState<CaloriePlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<PlanKind | null>(null)
  // Today until a mode is opened, at which point `open` clamps the prefill to
  // that mode's range. There is no form on screen before then.
  const [eventDate, setEventDate] = useState(localIsoDate)
  const [amount, setAmount] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [surplus, setSurplus] = useState<DaySurplus | null>(null)
  const [surplusFailed, setSurplusFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  const today = localIsoDate()

  const load = useCallback(() => {
    setLoading(true)
    api
      .getPlans()
      .then((next) => {
        setPlans(next)
        setError('')
      })
      // No plans and a failed fetch render identically otherwise, and one means
      // "nothing planned" while the other means "try again".
      .catch(() => setError("Couldn't load your calorie plans."))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  // The surplus is measured server-side, so it is fetched rather than derived.
  // Refetched on every change of the day in question because the answer moves:
  // logging another meal changes it, and so does changing your calorie goal.
  useEffect(() => {
    if (mode !== 'compensating') return
    let live = true
    setSurplus(null)
    setSurplusFailed(false)
    api
      .getDaySurplus(eventDate)
      .then((next) => {
        if (live) setSurplus(next)
      })
      .catch(() => {
        if (live) setSurplusFailed(true)
      })
    return () => {
      live = false
    }
  }, [mode, eventDate])

  // The days offered to absorb the change. Centred on the day being planned
  // for rather than always starting today, so funding a dinner three weeks out
  // offers the days around it instead of a fortnight of irrelevant ones.
  //
  // Never a day before today: a day whose meals are already logged cannot have
  // the target it was measured against changed after the fact. The server
  // enforces that too; this is what stops the user meeting the refusal.
  const candidates = useMemo(() => {
    const start = mode === 'planned' && addDays(eventDate, -7) > today
      ? addDays(eventDate, -7)
      : today
    return dayRange(start, MAX_PLAN_DAYS).filter(
      (day) => day !== eventDate && day >= today,
    )
  }, [mode, eventDate, today])

  // Days already claimed by another plan. Shown as unavailable rather than
  // offered and then refused: the server answers with a 409 naming the owner,
  // which is the right answer to a race but a poor way to learn the rule.
  const claimed = useMemo(() => {
    const taken = new Set<string>()
    for (const plan of plans) for (const day of plan.days) taken.add(day.date)
    return taken
  }, [plans])

  const open = (kind: PlanKind) => {
    setError('')
    setMode(kind)
    setSelected([])
    setAmount('')
    // Clamped to each mode's own legal range rather than used as given. The
    // prefill is whatever day the dashboard was showing, and that day is often
    // wrong for the mode being opened -- arriving from yesterday and choosing
    // "Plan a bigger day" would otherwise open the form on a date the server is
    // certain to refuse. A day to compensate for has to have happened; a day to
    // plan for cannot have.
    if (kind === 'compensating') {
      setEventDate(initialDate && initialDate <= today ? initialDate : addDays(today, -1))
    } else {
      setEventDate(initialDate && initialDate >= today ? initialDate : today)
    }
  }

  const close = () => {
    setError('')
    setMode(null)
    setSelected([])
  }

  const toggle = (day: string) => {
    setSelected((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    )
  }

  const submit = async () => {
    if (mode === null) return
    const moved = num(amount)
    const problem = validatePlan(selected, moved, mode === 'planned')
    if (problem) {
      onRejected(problem)
      return
    }

    setBusy(true)
    setError('')
    try {
      await api.createPlan({
        kind: mode,
        event_date: eventDate,
        // Sorted so the plan reads in date order the moment it comes back;
        // the server does not care, and the user does.
        dates: [...selected].sort(),
        calorie_delta: mode === 'planned' ? moved : null,
      })
      close()
      load()
    } catch (err) {
      // Server refusals arrive here whole -- every offending day at once,
      // because a plan is validated as a set. Shown next to the form rather
      // than in the shared modal: they are several sentences long and they
      // answer the thing still on screen.
      setError(
        err instanceof Error
          ? humaniseDates(err.message)
          : 'Could not save that plan.',
      )
    } finally {
      setBusy(false)
    }
  }

  const cancel = async (eventDay: string) => {
    setBusy(true)
    setError('')
    try {
      await api.cancelPlan(eventDay)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not cancel that plan.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card as="section" className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Calorie planning</h2>
        <p className="mt-1 text-sm text-slate-400">
          Move calories between days without changing the week. Plan a bigger
          day and fund it from the days around it, or spread a day that already
          ran over or under across the days ahead.
        </p>
        {/* The honest note, on screen rather than in a docstring. The app is
            not keeping a ledger and it is not going to collect: your measured
            expenditure is fitted from average intake against your weight
            trend, so one large day already shows up as a slightly slower week
            whether or not you do anything about it. */}
        <p className="mt-2 text-xs text-ink-faint">
          Nothing here is a debt. One big day already shows up as a slightly
          slower week on its own — this only lets you decide where it lands.
          Protein never moves; carbohydrate and fat absorb the difference.
          Plans apply straight away, without the Save bar.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-ink-faint">Loading…</p>
      ) : plans.length === 0 ? (
        <p className="text-sm text-ink-faint">Nothing planned.</p>
      ) : (
        <ul className="space-y-3">
          {plans.map((plan) => (
            <li
              key={plan.event_date}
              className="rounded-lg border border-slate-800 bg-slate-950 p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-200">
                  {plan.kind === 'planned'
                    ? `Planning for ${short(plan.event_date)}`
                    : `Making up ${short(plan.event_date)}`}
                </span>
                {/* GET /api/plan only returns plans with a day still ahead,
                    so this is always true today. Kept as a condition rather
                    than dropped: the server refuses to cancel a fully-past
                    plan with a 409, and if this list ever widens to show
                    finished plans, a Cancel button that 409s is the failure
                    that would appear. */}
                {plan.can_cancel && (
                  <button
                    onClick={() => cancel(plan.event_date)}
                    disabled={busy}
                    className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-60"
                  >
                    Cancel
                  </button>
                )}
              </div>
              <ul className="mt-2 space-y-1">
                {plan.days.map((day) => (
                  <li
                    key={day.date}
                    className="flex justify-between gap-3 text-xs text-slate-400"
                  >
                    <span className={day.date < today ? 'text-ink-faint' : ''}>
                      {short(day.date)}
                      {day.date < today && ' · already passed'}
                    </span>
                    <span>
                      {Math.round(day.calorie_goal).toLocaleString()} kcal
                      <span className="ml-1 text-ink-faint">
                        ({signed(day.calorie_delta ?? 0)})
                      </span>
                    </span>
                  </li>
                ))}
              </ul>

            </li>
          ))}
        </ul>
      )}

      {mode === null ? (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => open('planned')}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            Plan a bigger day
          </button>
          <button
            onClick={() => open('compensating')}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            Make up a day
          </button>
        </div>
      ) : (
        <div className="space-y-4 rounded-lg border border-slate-800 bg-slate-950 p-4">
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="block text-slate-400">
                {mode === 'planned' ? 'Day to plan for' : 'Day to make up'}
              </span>
              <input
                type="date"
                value={eventDate}
                // The mirror image of every other date input in this app. A
                // weigh-in or a meal can only describe something that has
                // happened; a plan is the one thing that reaches forward.
                min={mode === 'planned' ? today : undefined}
                max={
                  mode === 'planned'
                    ? addDays(today, MAX_PLAN_HORIZON_DAYS)
                    : today
                }
                onChange={(e) => {
                  if (!e.target.value) return
                  setEventDate(e.target.value)
                  setSelected([])
                }}
                className="mt-1 rounded border border-slate-800 bg-slate-900 px-2 py-1 text-slate-200"
              />
            </label>

            {mode === 'planned' && (
              <label className="text-sm">
                <span className="block text-slate-400">Calories to move</span>
                <input
                  type="number"
                  inputMode="numeric"
                  value={amount}
                  placeholder="600"
                  onChange={(e) => setAmount(e.target.value)}
                  className="mt-1 w-32 rounded border border-slate-800 bg-slate-900 px-2 py-1 text-slate-200"
                />
                <span className="mt-1 block text-xs text-ink-faint">
                  Negative for a deliberately smaller day.
                </span>
              </label>
            )}
          </div>

          {mode === 'compensating' && (
            <div className="text-sm">
              {surplusFailed ? (
                <p className="text-slate-400">
                  Couldn&apos;t work out how that day went. Try again.
                </p>
              ) : surplus === null ? (
                <p className="text-ink-faint">Checking that day…</p>
              ) : surplus.meal_count === 0 ? (
                <p className="text-slate-400">
                  Nothing is logged on {short(eventDate)}. A day with no meals
                  on it is a day nobody recorded, not a day of eating nothing —
                  there is nothing to spread.
                </p>
              ) : (
                <div className="space-y-1">
                  <p className="text-slate-300">
                    {Math.round(surplus.consumed_calories).toLocaleString()} kcal
                    eaten against a{' '}
                    {Math.round(surplus.reference_calories).toLocaleString()} kcal
                    target —{' '}
                    <span className="font-medium">
                      {signed(surplus.surplus_calories)} kcal
                    </span>
                    .
                  </p>
                  {/* Said plainly because it is a real limitation, not a
                      footnote: this app stores one calorie goal, not a
                      history of them, so a past day can only be measured
                      against the target it has now. */}
                  <p className="text-xs text-ink-faint">
                    Measured against that day&apos;s target as it stands now. If
                    you have changed your goal since, this number has moved with
                    it.
                  </p>
                </div>
              )}
            </div>
          )}

          <div>
            <p className="text-sm text-slate-400">
              {mode === 'planned'
                ? 'Days to fund it from'
                : 'Days to spread it across'}
              <span className="ml-1 text-xs text-ink-faint">
                ({selected.length} of up to {MAX_PLAN_DAYS})
              </span>
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidates.map((day) => {
                const taken = claimed.has(day)
                const on = selected.includes(day)
                return (
                  <button
                    key={day}
                    onClick={() => toggle(day)}
                    disabled={taken || busy}
                    title={taken ? 'Already adjusted by another plan' : undefined}
                    className={`rounded-lg border px-2.5 py-1 text-xs ${
                      on
                        ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300'
                        : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800'
                    } disabled:cursor-not-allowed disabled:opacity-35`}
                  >
                    {short(day)}
                  </button>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-ink-faint">
              Split evenly across the days you pick. The exact per-day targets
              come back from the server, which is also what refuses a spread
              that would take any day below your calorie floor.
            </p>
          </div>

          {error && <p className="text-sm text-rose-400">{error}</p>}

          <div className="flex items-center gap-3">
            <button
              onClick={submit}
              disabled={busy}
              className="rounded-lg bg-emerald-500 px-4 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {busy ? 'Saving…' : 'Save plan'}
            </button>
            <button
              onClick={close}
              disabled={busy}
              className="text-sm text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === null && error && <p className="text-sm text-rose-400">{error}</p>}
    </Card>
  )
}
