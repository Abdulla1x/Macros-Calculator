import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
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
import {
  adminHues,
  axisStroke,
  axisTick,
  barRadius,
  chartMargin,
  gridStroke,
  legendStyle,
  shortDate,
  tooltipLabelStyle,
  tooltipStyle,
  activeDot,
} from '../lib/chartTheme'
import type { AdminStats, AdminUserRow } from '../types'
import Card from '../components/ui/Card'


const plural = (count: number, noun: string) =>
  `${count} ${noun}${count === 1 ? '' : 's'}`

function relativeDay(iso: string | null): string {
  if (iso === null) return 'Never'
  const then = new Date(iso)
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days} days ago`
  return then.toISOString().slice(0, 10)
}

export default function Admin() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const [nextStats, nextUsers] = await Promise.all([
        api.getAdminStats(),
        api.getAdminUsers(),
      ])
      setStats(nextStats)
      setUsers(nextUsers)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load admin data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // The AI tile is the one number with operational consequences: exhausting
  // the global cap breaks meal analysis for every account at once.
  const aiShare = stats
    ? Math.round((stats.ai_calls_today / stats.ai_global_daily_limit) * 100)
    : 0

  const tiles = stats
    ? [
        { label: 'Accounts', value: String(stats.total_users) },
        {
          label: 'Active this week',
          value: String(stats.active_7d),
        },
        { label: 'Meals this week', value: stats.meals_7d.toLocaleString() },
        {
          label: 'AI calls today',
          value: `${stats.ai_calls_today} / ${stats.ai_global_daily_limit}`,
        },
      ]
    : []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Admin</h1>
        <p className="text-sm text-slate-400">
          Usage metrics only — no meal, food or weight content is shown here or
          sent by the API.
        </p>
      </header>

      {error && (
        <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error}{' '}
          <button onClick={load} className="underline hover:text-rose-200">
            Retry
          </button>
        </div>
      )}

      {loading && !stats && (
        <p className="text-sm text-ink-faint">Loading…</p>
      )}

      {stats && (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {tiles.map((tile) => (
              <Card pad="sm" key={tile.label}>
                <p className="text-xs text-slate-400">{tile.label}</p>
                <p className="mt-1 text-xl font-bold">{tile.value}</p>
              </Card>
            ))}
          </section>

          <Card as="section">
            <h2 className="text-sm font-semibold">Accounts per day</h2>
            <p className="mb-3 text-xs text-slate-400">
              Last {stats.window_days} days · {plural(stats.signups_30d, 'signup')}{' '}
              · {plural(stats.active_30d, 'account')} active at least once
            </p>
            {/* Both series count accounts, so they legitimately share one
                y-axis. Meals live in their own chart below rather than on a
                second axis here — a chart with two scales lets you draw any
                relationship you like between them. */}
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart
                data={stats.signups.map((point, index) => ({
                  date: point.date,
                  signups: point.count,
                  active: stats.activity[index]?.active_users ?? 0,
                }))}
                margin={chartMargin}
              >
                <CartesianGrid stroke={gridStroke} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={axisTick}
                  tickFormatter={shortDate}
                  stroke={axisStroke}
                />
                <YAxis tick={axisTick} stroke={axisStroke} allowDecimals={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                />
                <Legend wrapperStyle={legendStyle} />
                {/* Signups are discrete events, so they get bars; "active" is
                    a level that persists, so it gets a line. The differing
                    mark is a second channel carrying the same distinction the
                    colour does. */}
                <Bar
                  name="New signups"
                  dataKey="signups"
                  fill={adminHues.signups}
                  radius={barRadius}
                  isAnimationActive={false}
                />
                <Line
                  name="Active accounts"
                  type="monotone"
                  dataKey="active"
                  stroke={adminHues.active}
                  strokeWidth={2}
                  dot={false}
                  activeDot={activeDot(adminHues.active)}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          <Card as="section">
            <h2 className="text-sm font-semibold">Meals logged per day</h2>
            <p className="mb-3 text-xs text-slate-400">
              Counted on the day the meal was entered, not the day it was eaten.
            </p>
            {/* One series, so no legend — the heading names it. */}
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={stats.activity}
                margin={chartMargin}
              >
                <CartesianGrid stroke={gridStroke} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={axisTick}
                  tickFormatter={shortDate}
                  stroke={axisStroke}
                />
                <YAxis tick={axisTick} stroke={axisStroke} allowDecimals={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                />
                <Bar
                  name="Meals"
                  dataKey="meals"
                  fill={adminHues.meals}
                  radius={barRadius}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card as="section">
            <h2 className="mb-3 text-sm font-semibold">
              Accounts <span className="text-ink-faint">({users.length})</span>
            </h2>
            {users.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-faint">
                No accounts yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-slate-400">
                    <tr>
                      <th className="pb-2 pr-4 font-medium">Email</th>
                      <th className="pb-2 pr-4 font-medium">Joined</th>
                      <th className="pb-2 pr-4 font-medium">Last active</th>
                      <th className="pb-2 pr-4 text-right font-medium">Meals</th>
                      <th className="pb-2 pr-4 text-right font-medium">
                        Weigh-ins
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium">Foods</th>
                      <th className="pb-2 pr-4 text-right font-medium">Templates</th>
                      {/* The daily trackers, by their dashboard icons. Counts
                          only, never contents — a supplement name can disclose
                          a prescription, and a plan's date discloses a
                          calendar, so these columns say how many and never
                          which. */}
                      <th className="pb-2 pr-4 text-right font-medium" title="Water logs">
                        💧
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium" title="Days of steps logged">
                        👟
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium" title="Supplement doses ticked">
                        💊
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium" title="Days adjusted by a calorie plan">
                        📅
                      </th>
                      <th className="pb-2 text-right font-medium">AI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((row) => (
                      <tr key={row.id} className="border-t border-slate-800">
                        <td className="py-2 pr-4">{row.email}</td>
                        <td className="py-2 pr-4 text-slate-400">
                          {row.created_at.slice(0, 10)}
                        </td>
                        <td className="py-2 pr-4 text-slate-400">
                          {relativeDay(row.last_active_at)}
                        </td>
                        <td className="py-2 pr-4 text-right">{row.meals}</td>
                        <td className="py-2 pr-4 text-right">{row.weights}</td>
                        <td className="py-2 pr-4 text-right">{row.foods}</td>
                        <td className="py-2 pr-4 text-right">{row.meal_templates}</td>
                        <td className="py-2 pr-4 text-right">{row.water_logs}</td>
                        <td className="py-2 pr-4 text-right">{row.steps}</td>
                        <td
                          className="py-2 pr-4 text-right"
                          title={`${row.supplements} supplement${row.supplements === 1 ? '' : 's'} tracked`}
                        >
                          {row.supplement_logs}
                        </td>
                        <td className="py-2 pr-4 text-right">{row.calorie_plan_days}</td>
                        <td className="py-2 text-right">{row.ai_calls}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <p className="text-xs text-ink-faint">
            AI calls today: {stats.ai_calls_today} of{' '}
            {stats.ai_global_daily_limit} ({aiShare}% of the global cap).
            {Object.entries(stats.ai_calls_30d_by_kind).length > 0 && (
              <>
                {' '}
                Last {stats.window_days} days by kind:{' '}
                {Object.entries(stats.ai_calls_30d_by_kind)
                  .map(([kind, count]) => `${kind} ${count}`)
                  .join(', ')}
                .
              </>
            )}
          </p>
        </>
      )}
    </div>
  )
}
