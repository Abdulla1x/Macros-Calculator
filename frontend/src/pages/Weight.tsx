import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import { addDays, daysBetween, localIsoDate, parseIsoDate } from '../lib/dates'
import { displayToKg, formatRate, formatWeight, unitLabel } from '../lib/units'
import { useSettings } from '../settings/SettingsContext'
import {
  activeDot,
  axisStroke,
  axisTick,
  chartMargin,
  GOAL_COLOR,
  gridStroke,
  legendStyle,
  RAW_COLOR,
  shortDate,
  tooltipLabelStyle,
  tooltipStyle,
  TREND_COLOR,
} from '../lib/chartTheme'
import type {
  GoalProjection,
  Settings,
  WeightEntry,
  WeightTrend,
  WeightTrendPoint,
} from '../types'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'
import Field from '../components/ui/Field'
import Button from '../components/ui/Button'
import { useLiveMessage } from '../hooks/useLiveMessage'
import ShowAllToggle from '../components/ShowAllToggle'

// How much history is FETCHED -- the endpoint's own maximum, and deliberately
// not the range the chart happens to be showing.
//
// ⚠️ `days` on GET /api/weights/trend decides what the numbers are computed
// from, not just what is drawn: the EWMA seeds at the first entry in the window
// and the rate needs seven points inside 28 days. Wiring the picker below to it
// would move the trend weight, the weekly rate and the projected date every
// time someone zoomed the chart, and a short enough range would blank the last
// two outright. So the fetch is fixed and the picker slices what came back.
// Choosing which points to draw is a display decision; recomputing a number
// client-side is not, and this stays on the right side of that line.
const TREND_FETCH_DAYS = 1825

// What the picker offers. `days: null` is everything fetched -- five years,
// which is "all" for any real account and is what the endpoint will serve.
const RANGE_OPTIONS = [
  { days: 30, label: '30 days', heading: 'Last 30 days' },
  { days: 90, label: '90 days', heading: 'Last 90 days' },
  { days: 365, label: '1 year', heading: 'Last year' },
  { days: null, label: 'All', heading: 'All weigh-ins' },
] as const

// 90 by default, so the page opens on exactly what it always showed.
const DEFAULT_RANGE_DAYS: number | null = 90

// How many weigh-ins the history shows before it offers the rest. Ten rather
// than ShowAllToggle's COLLAPSED_ROWS of five -- see the note there on why the
// two library lists must agree with each other and this one need not.
const HISTORY_ROWS = 10

/** The points inside the picked range, or all of them. Display only. */
function pointsInRange(
  points: WeightTrendPoint[],
  days: number | null,
): WeightTrendPoint[] {
  if (days === null) return points
  const cutoff = addDays(localIsoDate(), -(days - 1))
  return points.filter((point) => point.date >= cutoff)
}

// What the page uses when the response has no `projection` at all.
//
// Not defensive programming for its own sake, and not a type the API can
// return: the frontend ships from Vercel and the API from Render,
// independently, so for a minute after any release this page runs against a
// backend that predates the field. Reading through `trend.projection`
// unguarded in that gap throws and replaces the whole Weight page with the
// error boundary. AILatencyCard in Admin.tsx carries the same `??` for the
// same reason, and its comment records that the bug was caught exactly that
// way rather than reasoned about.
const NO_PROJECTION: GoalProjection = {
  status: 'no_goal',
  goal_weight_kg: null,
  remaining_kg: null,
  weeks: null,
  reach_date: null,
  from_date: null,
}

/** A date far enough ahead that the year matters. Every other date in this app
 *  drops it; a projection is the one that can land in another year. */
const longDate = (iso: string) =>
  parseIsoDate(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })


export default function Weight() {
  const { settings, reload: reloadSettings } = useSettings()
  const [entries, setEntries] = useState<WeightEntry[]>([])
  const [trend, setTrend] = useState<WeightTrend | null>(null)
  const [date, setDate] = useState(localIsoDate)
  const [weight, setWeight] = useState('')
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  useLiveMessage(error)
  useLiveMessage(status === 'saved' ? 'Weigh-in saved' : '')
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [rangeDays, setRangeDays] = useState<number | null>(DEFAULT_RANGE_DAYS)
  const [historyExpanded, setHistoryExpanded] = useState(false)

  const unit = settings?.weight_unit ?? 'kg'
  const label = unitLabel(unit)

  const load = useCallback(() => {
    setError(null)
    // A failed load must not look like "you have never weighed yourself".
    api.getWeights().then(setEntries).catch(() => {
      setEntries([])
      setError("Couldn't load your weight log — check your connection and try again.")
    })
    api.getWeightTrend(TREND_FETCH_DAYS).then(setTrend).catch(() => setTrend(null))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Prefill with the most recent weigh-in: the next one is usually close to it,
  // so this is a nudge, not a default that hides a typo.
  const latest = entries.length > 0 ? entries[entries.length - 1] : null
  useEffect(() => {
    if (latest && weight === '') setWeight(formatWeight(latest.weight_kg, unit))
    // Only seeds the empty field; it must not fight the user as they type.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest, unit])

  const existingForDate = entries.find((entry) => entry.date === date) ?? null

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    const typed = Number(weight)
    if (!Number.isFinite(typed) || typed <= 0) {
      setError(`Enter a weight in ${label}.`)
      return
    }
    setStatus('saving')
    setError(null)
    try {
      await api.saveWeight({ date, weight_kg: displayToKg(typed, unit) })
      setStatus('saved')
      load()
      // A weigh-in is an input to the calorie target, so on an account with
      // "work out my goals from my body profile" turned on the server has just
      // rewritten the four goals. Without this refetch the Dashboard rings
      // would keep drawing against the old ones until the app remounted.
      reloadSettings()
    } catch (err) {
      setStatus('idle')
      setError(err instanceof Error ? err.message : 'Could not save that weigh-in.')
    }
  }

  const remove = async (id: number) => {
    try {
      await api.deleteWeight(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed — try again.')
      return
    } finally {
      setConfirmDelete(null)
    }
    load()
  }

  const range =
    RANGE_OPTIONS.find((option) => option.days === rangeDays) ?? RANGE_OPTIONS[1]
  const visiblePoints = pointsInRange(trend?.points ?? [], rangeDays)
  const chartData = visiblePoints.map((point) => ({
    date: point.date,
    weight: Number(formatWeight(point.weight_kg, unit)),
    trend: Number(formatWeight(point.trend_kg, unit)),
  }))

  // Newest first, then capped. The cap applies to the reversed array so
  // collapsing keeps the most recent weigh-ins rather than the oldest.
  const ordered = [...entries].reverse()
  const visibleEntries = historyExpanded ? ordered : ordered.slice(0, HISTORY_ROWS)
  const goalKg = (trend?.projection ?? NO_PROJECTION).goal_weight_kg

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Weight</h1>
        <p className="text-sm text-slate-400">
          Log a weigh-in and watch the trend, not the daily noise.
        </p>
      </header>

      {error && (
        <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>
      )}

      <Card as="section">
        <h2 className="mb-3 font-semibold">Log a weigh-in</h2>
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <Field label="Date">
            <TextInput
              type="date"
              value={date}
              max={localIsoDate()}
              onChange={(event) => {
                setDate(event.target.value)
                setStatus('idle')
              }}
              className="w-full"
            />
          </Field>
          <Field label={<>Weight ({label})</>}>
            <TextInput
              type="number"
              step="0.1"
              min="0"
              inputMode="decimal"
              value={weight}
              onChange={(event) => {
                setWeight(event.target.value)
                setStatus('idle')
              }}
              className="w-full"
            />
          </Field>
          <Button
            type="submit"
            disabled={status === 'saving'}
            className="px-5 py-2"
          >
            {status === 'saving' ? 'Saving…' : existingForDate ? 'Update' : 'Save'}
          </Button>
          {status === 'saved' && <span className="text-sm text-emerald-400">Saved ✓</span>}
        </form>
        {/* One weigh-in per day, so re-saving a date is a correction. Said out
            loud here, or the missing second row reads as a lost entry. */}
        <p className="mt-3 text-xs text-ink-faint">
          {existingForDate
            ? `Replaces the ${formatWeight(existingForDate.weight_kg, unit)} ${label} already logged for this day.`
            : `One weigh-in per day — saving the same date again replaces it. Change ${label} in Settings.`}
        </p>
      </Card>

      <Card as="section">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <h2 className="font-semibold">{range.heading}</h2>
          {/* "shown", not "logged". With a fixed fetch this counts the drawn
              slice, while TrendReadout below keeps reporting the full sample
              the trend was smoothed over -- two different numbers, each saying
              what it counts. */}
          {visiblePoints.length > 0 && (
            <p className="text-xs text-ink-faint">
              {visiblePoints.length} weigh-in{visiblePoints.length === 1 ? '' : 's'} shown
            </p>
          )}
          <RangePicker value={rangeDays} onChange={setRangeDays} />
        </div>

        {chartData.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chartData} margin={chartMargin}>
                <CartesianGrid stroke={gridStroke} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={axisTick}
                  tickFormatter={shortDate}
                  stroke={axisStroke}
                />
                {/* Not zero-based: body weight varies by a few percent, and a
                    0-anchored axis would flatten every real change to nothing. */}
                <YAxis
                  tick={axisTick}
                  stroke={axisStroke}
                  domain={['dataMin - 1', 'dataMax + 1']}
                  tickFormatter={(value: number) => value.toFixed(1)}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                  formatter={(value) => `${Number(value).toFixed(1)} ${label}`}
                />
                <Legend wrapperStyle={legendStyle} />
                {/* Fed from the projection rather than from settings, so the
                    line and the sentence under the chart can never name two
                    different goals.

                    ifOverflow is set rather than inherited, and it matters:
                    the YAxis above carries an explicit domain, so recharts
                    would otherwise DISCARD a goal that falls outside it -- the
                    line would silently vanish for exactly the people whose
                    goal is furthest away. Extending squashes the series when
                    the goal is distant, which is the trade taken knowingly: a
                    goal line you cannot see is not a feature, and the
                    compression is itself honest about the distance. */}
                {goalKg !== null && (
                  <ReferenceLine
                    y={Number(formatWeight(goalKg, unit))}
                    stroke={GOAL_COLOR}
                    strokeDasharray="4 4"
                    ifOverflow="extendDomain"
                    label={{
                      value: `Goal ${formatWeight(goalKg, unit)} ${label}`,
                      position: 'insideBottomLeft',
                      fill: GOAL_COLOR,
                      fontSize: 11,
                    }}
                  />
                )}
                {/* strokeWidth 0 rather than stroke "none": the dots are the
                    mark, but the legend swatch still needs a colour to draw,
                    or this series is identified by its label alone. */}
                <Line
                  name="Weigh-in"
                  type="monotone"
                  dataKey="weight"
                  stroke={RAW_COLOR}
                  strokeWidth={0}
                  legendType="circle"
                  dot={{ r: 4, fill: RAW_COLOR, stroke: 'none' }}
                  activeDot={activeDot(RAW_COLOR)}
                  isAnimationActive={false}
                />
                <Line
                  name="Trend"
                  type="monotone"
                  dataKey="trend"
                  stroke={TREND_COLOR}
                  strokeWidth={2}
                  legendType="plainline"
                  dot={false}
                  activeDot={activeDot(TREND_COLOR)}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
            <TrendReadout trend={trend} unit={unit} />
          </>
        ) : (
          <p className="py-6 text-center text-sm text-ink-faint">
            No weigh-ins yet — log one above and the chart starts here.
          </p>
        )}
      </Card>

      <Card as="section">
        <h2 className="mb-3 font-semibold">History</h2>
        {entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-faint">Nothing logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800">
            {visibleEntries.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-3 py-2.5">
                <div>
                  <p className="text-sm font-medium">
                    {formatWeight(entry.weight_kg, unit)} {label}
                  </p>
                  <p className="text-xs text-slate-400">{entry.date}</p>
                </div>
                {confirmDelete === entry.id ? (
                  <span className="flex items-center gap-2 text-xs">
                    <button
                      onClick={() => remove(entry.id)}
                      className="rounded bg-rose-500/20 px-2 py-1 text-rose-300 hover:bg-rose-500/30"
                    >
                      Delete
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="rounded bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700"
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <span className="flex items-center gap-3">
                    {/* ⚠ `title` is not a name here. A button's CONTENTS win the
                        accessible-name computation whenever they are non-empty,
                        so these two announced as "✎" and "✕" and the title was
                        never read. And a name has to identify WHICH row: every
                        entry in this list rendered the same pair, so "delete"
                        on its own names one of thirty identical controls. axe
                        cannot see either problem -- the glyph is a non-empty
                        name, so the button passes. */}
                    <button
                      onClick={() => {
                        setDate(entry.date)
                        setWeight(formatWeight(entry.weight_kg, unit))
                        setStatus('idle')
                        window.scrollTo({ top: 0, behavior: 'smooth' })
                      }}
                      className="text-xs text-ink-faint hover:text-emerald-400"
                      aria-label={`Edit the weigh-in from ${entry.date}`}
                    >
                      <span aria-hidden="true">✎</span>
                    </button>
                    <button
                      onClick={() => setConfirmDelete(entry.id)}
                      className="text-xs text-ink-faint hover:text-rose-400"
                      aria-label={`Delete the weigh-in from ${entry.date}`}
                    >
                      <span aria-hidden="true">✕</span>
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <ShowAllToggle
          total={ordered.length}
          cap={HISTORY_ROWS}
          expanded={historyExpanded}
          onToggle={() => {
            setHistoryExpanded((current) => !current)
            // An armed delete must not survive out of sight, for the reason
            // FoodLibrarySection gives: a row scrolled away still holding its
            // confirmation comes back armed, one tap from deleting something
            // the user had already moved on from.
            setConfirmDelete(null)
          }}
          noun="weigh-in"
        />
      </Card>
    </div>
  )
}

/** Which slice of the history the chart draws. Chart only -- it never reaches
 *  the server, and it deliberately does not filter the history list below.
 *  A control in one card that silently reshaped another would be hidden, and
 *  someone hunting an old typo to delete would have to discover that the
 *  chart's zoom was also a list filter.
 *
 *  Buttons with aria-pressed inside a labelled group rather than a radio set:
 *  this toggles what is drawn, it does not submit a value. The group label is
 *  the part that matters and the part an audit cannot check -- axe accepts an
 *  unlabelled group of buttons happily. */
function RangePicker({
  value,
  onChange,
}: {
  value: number | null
  onChange: (days: number | null) => void
}) {
  return (
    <div role="group" aria-label="Chart range" className="flex flex-wrap gap-1.5">
      {RANGE_OPTIONS.map((option) => {
        const active = option.days === value
        return (
          <button
            key={option.heading}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.days)}
            className={`rounded-control border px-2.5 py-1 text-xs ${
              active
                ? 'border-brand bg-brand/10 font-semibold text-brand'
                : 'border-line-strong text-ink-muted hover:border-brand hover:text-brand'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/** The two derived numbers, each next to what it was computed from. Neither is
 * a measurement, and the page should not let them look like one. */
function TrendReadout({
  trend,
  unit,
}: {
  trend: WeightTrend | null
  unit: Settings['weight_unit']
}) {
  if (!trend) return null
  const label = unitLabel(unit)
  const goal = trend.projection ?? NO_PROJECTION

  return (
    <dl className="mt-4 grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
      <div>
        <dt className="text-xs text-slate-400">Trend weight</dt>
        {/* The swatch ties this number to the line on the chart; the number
            itself stays in text ink rather than wearing the series colour. */}
        <dd className="flex items-center gap-2 text-lg font-semibold">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: TREND_COLOR }}
          />
          {trend.latest_trend_kg === null
            ? '—'
            : `${formatWeight(trend.latest_trend_kg, unit)} ${label}`}
        </dd>
        {/* A second <dd>, not a <p>: a <div> inside a <dl> may hold only
            <dt>/<dd>, and one term may have several descriptions. */}
        <dd className="mt-0.5 text-xs text-ink-faint">
          Smoothed over {trend.point_count} weigh-in
          {trend.point_count === 1 ? '' : 's'}, weighted towards recent ones.
        </dd>
      </div>
      <div>
        <dt className="text-xs text-slate-400">Weekly change</dt>
        <dd className="text-lg font-semibold">
          {trend.weekly_rate_kg === null
            ? '—'
            : `${formatRate(trend.weekly_rate_kg, unit)} ${label}/week`}
        </dd>
        <dd className="mt-0.5 text-xs text-ink-faint">
          {trend.weekly_rate_kg === null
            ? 'Needs at least 7 weigh-ins in the last 28 days.'
            : 'Fitted to the trend line over the last 28 days.'}
        </dd>
      </div>
      {/* Spans both columns: the two above are numbers, this one is a
          sentence. A <dt>/<dd> pair like its neighbours and not a <p> -- a
          bare paragraph inside a <dl> group is invalid, and was one of the
          four real defects the accessibility audit turned up. */}
      <div className="sm:col-span-2">
        <dt className="text-xs text-slate-400">Goal weight</dt>
        <dd className="flex items-center gap-2 text-lg font-semibold">
          {goal.goal_weight_kg !== null && (
            <span
              aria-hidden="true"
              className="inline-block h-0.5 w-3 shrink-0"
              style={{ background: GOAL_COLOR }}
            />
          )}
          {goal.goal_weight_kg === null
            ? '—'
            : `${formatWeight(goal.goal_weight_kg, unit)} ${label}`}
        </dd>
        <dd className="mt-0.5 text-xs text-ink-faint">
          {projectionCaption(trend, unit)}
        </dd>
      </div>
    </dl>
  )
}

/** The projection, as a sentence. Assembled here rather than server-side
 *  because it has to name a weight in the reader's own unit and a date in
 *  their own locale, and the server knows neither.
 *
 *  Every branch is driven by `status`, never by which fields are null: the
 *  server decides what it is willing to claim, and this only says it. */
function projectionCaption(trend: WeightTrend, unit: Settings['weight_unit']): string {
  const goal = trend.projection ?? NO_PROJECTION
  const rate = trend.weekly_rate_kg
  const label = unitLabel(unit)
  // Signed towards the goal, so the sign is the direction and the magnitude is
  // the gap. A rate conversion works on a difference for the same reason it
  // works on a weight -- both scales are linear through zero.
  const gap =
    goal.remaining_kg === null
      ? ''
      : `${formatWeight(Math.abs(goal.remaining_kg), unit)} ${label} ` +
        `${goal.remaining_kg < 0 ? 'to lose' : 'to gain'}`

  switch (goal.status) {
    case 'no_goal':
      return "Set a goal weight in Settings and we'll work out when you would reach it."
    case 'reached':
      return goal.from_date === null
        ? 'You are there.'
        : `You were there at your weigh-in on ${longDate(goal.from_date)}.`
    case 'no_rate':
      return 'Needs at least 7 weigh-ins in the last 28 days before a date can be worked out.'
    case 'stale':
      return goal.from_date === null
        ? 'No recent weigh-ins to project from.'
        : `Your last weigh-in was ${daysBetween(goal.from_date, localIsoDate())} days ago, so there is no current rate to project from.`
    case 'holding':
      return `${gap}, but your weight is holding steady — no date to give.`
    case 'moving_away':
      return `${gap}, and the trend is currently going the other way.`
    case 'too_far':
      return `${gap}. At your current rate that is more than two years out, so we will not name a date.`
    case 'on_course':
      // Both are always set alongside this status. Guarded anyway because the
      // alternative to a fallback here is longDate('') throwing, which takes
      // the page down rather than degrading the sentence.
      return goal.reach_date === null || rate === null
        ? `${gap}.`
        : `${gap}. At your measured ${formatRate(rate, unit)} ${label}/week, around ${longDate(goal.reach_date)}.`
  }
}
