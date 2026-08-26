import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import { localIsoDate } from '../lib/dates'
import { displayToKg, formatRate, formatWeight, unitLabel } from '../lib/units'
import { useSettings } from '../settings/SettingsContext'
import type { Settings, WeightEntry, WeightTrend } from '../types'

// Emphasis form: the trend line is the subject, the raw weigh-ins are context.
// One accent hue plus the de-emphasis gray — validated against this app's chart
// surface (#0f172a) for lightness band, CVD separation and contrast.
const TREND_COLOR = '#3b82f6'
const RAW_COLOR = '#64748b'

// How far back the chart looks. The rate is fitted over a shorter window by the
// server; this is just how much history is drawn.
const CHART_DAYS = 90

const cardClass = 'rounded-xl border border-slate-800 bg-slate-900 p-5'
const fieldClass =
  'w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none'

export default function Weight() {
  const { settings, reload: reloadSettings } = useSettings()
  const [entries, setEntries] = useState<WeightEntry[]>([])
  const [trend, setTrend] = useState<WeightTrend | null>(null)
  const [date, setDate] = useState(localIsoDate)
  const [weight, setWeight] = useState('')
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const unit = settings?.weight_unit ?? 'kg'
  const label = unitLabel(unit)

  const load = useCallback(() => {
    setError(null)
    // A failed load must not look like "you have never weighed yourself".
    api.getWeights().then(setEntries).catch(() => {
      setEntries([])
      setError("Couldn't load your weight log — check your connection and try again.")
    })
    api.getWeightTrend(CHART_DAYS).then(setTrend).catch(() => setTrend(null))
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

  const chartData = (trend?.points ?? []).map((point) => ({
    date: point.date,
    weight: Number(formatWeight(point.weight_kg, unit)),
    trend: Number(formatWeight(point.trend_kg, unit)),
  }))

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold">Weight</h2>
        <p className="text-sm text-slate-400">
          Log a weigh-in and watch the trend, not the daily noise.
        </p>
      </header>

      {error && (
        <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>
      )}

      <section className={cardClass}>
        <h3 className="mb-3 font-semibold">Log a weigh-in</h3>
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Date</span>
            <input
              type="date"
              value={date}
              max={localIsoDate()}
              onChange={(event) => {
                setDate(event.target.value)
                setStatus('idle')
              }}
              className={fieldClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-400">Weight ({label})</span>
            <input
              type="number"
              step="0.1"
              min="0"
              inputMode="decimal"
              value={weight}
              onChange={(event) => {
                setWeight(event.target.value)
                setStatus('idle')
              }}
              className={fieldClass}
            />
          </label>
          <button
            type="submit"
            disabled={status === 'saving'}
            className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {status === 'saving' ? 'Saving…' : existingForDate ? 'Update' : 'Save'}
          </button>
          {status === 'saved' && <span className="text-sm text-emerald-400">Saved ✓</span>}
        </form>
        {/* One weigh-in per day, so re-saving a date is a correction. Said out
            loud here, or the missing second row reads as a lost entry. */}
        <p className="mt-3 text-xs text-ink-faint">
          {existingForDate
            ? `Replaces the ${formatWeight(existingForDate.weight_kg, unit)} ${label} already logged for this day.`
            : `One weigh-in per day — saving the same date again replaces it. Change ${label} in Settings.`}
        </p>
      </section>

      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h3 className="font-semibold">Last {CHART_DAYS} days</h3>
          {trend && trend.point_count > 0 && (
            <p className="text-xs text-ink-faint">
              {trend.point_count} weigh-in{trend.point_count === 1 ? '' : 's'} logged
            </p>
          )}
        </div>

        {chartData.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={(value: string) => value.slice(5)}
                  stroke="#334155"
                />
                {/* Not zero-based: body weight varies by a few percent, and a
                    0-anchored axis would flatten every real change to nothing. */}
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  stroke="#334155"
                  domain={['dataMin - 1', 'dataMax + 1']}
                  tickFormatter={(value: number) => value.toFixed(1)}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: 8,
                  }}
                  labelStyle={{ color: '#e2e8f0' }}
                  formatter={(value) => `${Number(value).toFixed(1)} ${label}`}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
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
                  activeDot={{ r: 5, fill: RAW_COLOR, stroke: '#0f172a', strokeWidth: 2 }}
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
                  activeDot={{ r: 5, fill: TREND_COLOR, stroke: '#0f172a', strokeWidth: 2 }}
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
      </section>

      <section className={cardClass}>
        <h3 className="mb-3 font-semibold">History</h3>
        {entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-faint">Nothing logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800">
            {[...entries].reverse().map((entry) => (
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
                    <button
                      onClick={() => {
                        setDate(entry.date)
                        setWeight(formatWeight(entry.weight_kg, unit))
                        setStatus('idle')
                        window.scrollTo({ top: 0, behavior: 'smooth' })
                      }}
                      className="text-xs text-ink-faint hover:text-emerald-400"
                      title="Edit this weigh-in"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => setConfirmDelete(entry.id)}
                      className="text-xs text-ink-faint hover:text-rose-400"
                      title="Delete this weigh-in"
                    >
                      ✕
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
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
        <p className="mt-0.5 text-xs text-ink-faint">
          Smoothed over {trend.point_count} weigh-in
          {trend.point_count === 1 ? '' : 's'}, weighted towards recent ones.
        </p>
      </div>
      <div>
        <dt className="text-xs text-slate-400">Weekly change</dt>
        <dd className="text-lg font-semibold">
          {trend.weekly_rate_kg === null
            ? '—'
            : `${formatRate(trend.weekly_rate_kg, unit)} ${label}/week`}
        </dd>
        <p className="mt-0.5 text-xs text-ink-faint">
          {trend.weekly_rate_kg === null
            ? 'Needs at least 7 weigh-ins in the last 28 days.'
            : 'Fitted to the trend line over the last 28 days.'}
        </p>
      </div>
    </dl>
  )
}
