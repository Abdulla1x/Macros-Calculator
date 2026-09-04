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
import type { AdminStats, AdminUserRow, KeepWarmStatus } from '../types'
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

/** A duration an operator reads at a glance. Seconds below a minute, because
 * "up 40 seconds" is the whole point of the cold verdict and "up 0m" hides it. */
function duration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

/** A wall-clock time on the window's own clock, so a boot time and the window
 * it falls in can be compared without doing timezone arithmetic in your head.
 *
 * Falls back to the browser's zone if Intl rejects the name. The zone is a
 * server-side constant so that should never happen — but this is the page you
 * open to find out what is broken, and it must not be the page that throws. */
function clockTime(iso: string, timeZone: string): string {
  const at = new Date(iso)
  try {
    return at.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone,
    })
  } catch {
    return at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  }
}

const hourLabel = (hour: number) => `${String(hour).padStart(2, '0')}:00`

/** The panel's whole argument, in one sentence.
 *
 * "Up 10 hours at 3 PM proves the pings work; up 40 seconds proves they do not,
 * because the page load was itself the cold start." The server decides which of
 * the five states holds; this only says what each one means. The spin-down
 * figure comes from the response rather than being written in here, so the copy
 * cannot drift from the number the verdict was computed against.
 */
function verdictCopy(status: KeepWarmStatus): { dot: string; text: string } {
  const spinDownMins = Math.round(status.spin_down_seconds / 60)
  const spinDown = `${spinDownMins}-minute`
  switch (status.verdict) {
    case 'warm':
      return {
        dot: 'text-emerald-500',
        text: `Awake for longer than the ${spinDown} spin-down, with marked pings still arriving. The scheduler is landing.`,
      }
    case 'warming':
      return {
        dot: 'text-amber-500',
        text: `Awake, but not yet past the ${spinDown} spin-down, so this proves nothing either way. Reload in a few minutes.`,
      }
    case 'cold':
      // Amber, not red, because this state has two causes and the panel cannot
      // see which: a deploy restarts the process too, and reporting a fresh
      // deploy as a broken scheduler would cry wolf after every single one.
      // Naming both is the honest version — and the second explanation is one
      // the operator can rule out instantly, which is what makes it useful.
      return {
        dot: 'text-amber-500',
        text: 'This process started moments ago. Either the server was asleep and opening this page is what woke it — in which case the pings are not landing, so check the cron-job.org job is enabled and its history is not all failures — or it has just been redeployed.',
      }
    case 'awaiting_marked_pings':
      // Almost always the rollout gap rather than a fault: this code can ship
      // before anyone edits the cron-job.org URL. Calling that "the scheduler
      // stopped" would be a guaranteed false alarm on its own deploy.
      return {
        dot: 'text-amber-500',
        text: 'No ping carrying ?src=keepwarm has arrived since boot. If the cron-job.org job has not been pointed at that URL yet, that is why — until it is, only uptime here means anything.',
      }
    case 'pings_missing':
      return {
        dot: 'text-rose-400',
        text: `Marked pings were arriving and have not for ${spinDownMins} minutes. Something else is keeping this up — ordinary traffic, most likely — and it will sleep as soon as that stops.`,
      }
    case 'outside_window':
      return {
        dot: 'text-ink-faint',
        text: 'Outside the ping window, so sleeping is expected and a cold start here is the intended cost of the free plan.',
      }
  }
}

/** One label/value pair on the keep-warm card.
 *
 * `live` marks a value that changes on its own between page loads. It is read
 * by scripts/dom-snapshot.mjs, which blanks these before comparing — without it
 * /admin would report a difference on every single run, and a harness that
 * always cries wolf stops being read. It doubles as a note to anyone reading
 * this file about which figures here are not reproducible.
 */
function KeepWarmFact({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold" data-live={label}>
        {value}
      </dd>
      {note !== undefined && (
        <dd className="text-xs text-ink-faint" data-live={`${label} note`}>
          {note}
        </dd>
      )}
    </div>
  )
}


/** The operator half of the cold-start work: is the pinger actually landing.
 *
 * Its own component so the verdict is computed once rather than per element,
 * and so Admin's already-long body is not carrying a fifth section inline.
 */
function KeepWarmCard({ status }: { status: KeepWarmStatus }) {
  const verdict = verdictCopy(status)
  return (
    <Card as="section">
      <h2 className="text-sm font-semibold">Keep-warm</h2>
      <p className="mb-3 text-xs text-slate-400">
        Whether the free instance is actually being kept awake. Held in
        the API process's memory, so every figure here resets when it
        sleeps — which is the point: a long uptime is itself the proof.
      </p>
      <p className="text-sm">
        <span className={verdict.dot}>●</span>{' '}
        <span data-live="verdict">{verdict.text}</span>
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KeepWarmFact
          label="Up"
          value={duration(status.uptime_seconds)}
          note={`since ${clockTime(status.booted_at, status.window_tz)}`}
        />
        <KeepWarmFact
          label="Scheduler pings"
          value={status.scheduler_pings.toLocaleString()}
          note={
            status.seconds_since_scheduler_ping === null
              ? 'none since boot'
              : status.seconds_since_scheduler_ping < 10
                ? // "last 0s ago" is technically correct and reads like a bug.
                  'seconds ago'
                : `${duration(status.seconds_since_scheduler_ping)} ago`
          }
        />
        <KeepWarmFact
          label="Longest gap"
          value={
            status.longest_scheduler_gap_seconds === null
              ? '—'
              : duration(status.longest_scheduler_gap_seconds)
          }
          note={`between scheduler pings · sleeps after ${Math.round(status.spin_down_seconds / 60)}m`}
        />
        <KeepWarmFact
          label="Window"
          value={`${hourLabel(status.window_start_hour)}–${hourLabel(status.window_end_hour)}`}
          note={`${status.window_tz} · now ${status.window_local_time} there`}
        />
      </dl>
      <p className="mt-3 text-xs text-ink-faint">
        Only pings to{' '}
        <code className="text-ink-muted">/api/health?src=keepwarm</code> are
        counted above. Render&apos;s own monitor hits the bare route roughly
        every four seconds and has done so{' '}
        <span data-live="total checks">
          {status.health_checks.toLocaleString()}
        </span>{' '}
        times since boot — counting those as scheduler pings is what made this
        panel&apos;s first version unable to detect anything at all.
      </p>
      <p className="mt-2 text-xs text-ink-faint">
        The window above is what this repository records. The schedule
        itself lives at cron-job.org and is the thing to edit — pings run
        every 10 minutes and its 30-second timeout means the first one
        each morning is logged as a failure while still starting the
        boot.
      </p>
    </Card>
  )
}

export default function Admin() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [keepWarm, setKeepWarm] = useState<KeepWarmStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const [nextStats, nextUsers, nextKeepWarm] = await Promise.all([
        api.getAdminStats(),
        api.getAdminUsers(),
        api.getKeepWarm(),
      ])
      setStats(nextStats)
      setUsers(nextUsers)
      setKeepWarm(nextKeepWarm)
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

          {keepWarm && <KeepWarmCard status={keepWarm} />}

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
