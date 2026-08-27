import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import MacroRing from '../components/MacroRing'
import ShareCodePanel from '../components/ShareCodePanel'
import StepsCard from '../components/StepsCard'
import SupplementsCard from '../components/SupplementsCard'
import WaterCard from '../components/WaterCard'
import {
  axisStroke,
  axisTick,
  chartMargin,
  macroHues,
  shortDate,
  tooltipLabelStyle,
  tooltipStyle,
} from '../lib/chartTheme'
import { addDays, localIsoDate, parseIsoDate } from '../lib/dates'
import { byRecentUse, rememberTemplate } from '../lib/recentTemplates'
import { useSettings } from '../settings/SettingsContext'
import type { AnalyticsSummary, Meal, MealTemplate, PlanDay } from '../types'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'
import { primaryButtonClass } from '../components/ui/Button'

// What the caption under the calorie ring says, if anything.
//
// Only the calorie ring gets one. Protein does not move under a plan at all,
// and captioning carbs and fat with the same sentence three times would be
// noise around a fact that belongs to the day, not to each macro.
function planCaption(plan: PlanDay | null, failed: boolean): string | undefined {
  if (failed) {
    return "Couldn't check for a plan on this day — showing your usual target."
  }
  if (!plan || plan.calorie_delta === null) return undefined

  const sign = plan.calorie_delta > 0 ? '+' : '−'
  const moved = `${sign}${Math.abs(Math.round(plan.calorie_delta))} kcal`
  // The event day of a planned group is one of its own adjusted days, so this
  // is the day being planned for rather than a day funding one.
  if (plan.event_date === plan.date) return `${moved} — a day you planned for`

  const when = plan.event_date
    ? parseIsoDate(plan.event_date).toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })
    : null
  if (!when) return moved
  return plan.kind === 'planned'
    ? `${moved} — funding ${when}`
    : `${moved} — making up ${when}`
}

// How many quick-log buttons show before the rest are folded away. Six fills
// three rows of two on a phone and two rows of three from `sm` up, which is
// about as much as can sit above the fold without pushing the trackers off it.
// The server caps a listing at 50 and nothing caps how many you can create, so
// without a limit here one prolific week buries the whole page.
const QUICK_LOG_VISIBLE = 6

export default function Dashboard() {
  const { settings } = useSettings()
  const { user } = useAuth()
  const [meals, setMeals] = useState<Meal[]>([])
  const [week, setWeek] = useState<AnalyticsSummary | null>(null)
  const [templates, setTemplates] = useState<MealTemplate[]>([])
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [browsingTemplates, setBrowsingTemplates] = useState(false)
  const [templateFilter, setTemplateFilter] = useState('')
  // Lifted here rather than held per-row so only one panel is ever open,
  // the same reason confirmDelete above is a single id and not a set.
  const [shareCode, setShareCode] = useState<{ label: string; code: string } | null>(
    null,
  )
  const [shareError, setShareError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [planDay, setPlanDay] = useState<PlanDay | null>(null)
  const [planFailed, setPlanFailed] = useState(false)
  const [viewedDate, setViewedDate] = useState(localIsoDate)
  const todayRef = useRef(localIsoDate())
  const realToday = localIsoDate()
  const isToday = viewedDate === realToday

  // When the tab regains focus past midnight, roll the view forward — but only
  // if the user is still on "today", so a day they deliberately navigated to
  // isn't clobbered. Same-string updates are no-ops.
  useEffect(() => {
    const refresh = () => {
      const now = localIsoDate()
      setViewedDate((prev) => (prev === todayRef.current ? now : prev))
      todayRef.current = now
    }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])

  const load = useCallback(() => {
    const today = localIsoDate()
    setError(null)
    // A failed load must not masquerade as an empty day.
    api.getMeals(viewedDate).then(setMeals).catch(() => {
      setMeals([])
      setError("Couldn't load your meals — check your connection and try again.")
    })
    // The 7-day trend stays anchored to the real today, independent of the day
    // being viewed — and it STOPS AT YESTERDAY.
    //
    // The analytics endpoint divides by calendar days in the range, so a range
    // ending today counts a half-finished day as a whole one: at lunchtime the
    // average reads hundreds of kcal below what is actually being eaten, which
    // is exactly when someone checks it. Seven *complete* days is still a
    // seven-day window, and it is the only one whose average means anything
    // before bedtime.
    //
    // It also settles a calendar disagreement: the server clamps the range end
    // to its own UTC today, while these dates are local. An end date always in
    // the past makes that clamp a no-op instead of a timezone-dependent one.
    api
      .getAnalytics(addDays(today, -7), addDays(today, -1))
      .then(setWeek)
      .catch(() => setWeek(null))
    // The targets actually in force on the viewed day. These are NOT
    // settings.calorie_goal: a calorie plan adjusts a single day, and the
    // server composes the adjustment on top of the stored goals. Resolved
    // there and never recomputed here -- a second definition of these numbers
    // in the client is a second thing that can be wrong, and this one would be
    // wrong invisibly, as a ring quietly drawn against the wrong target.
    api
      .getPlanDay(viewedDate)
      .then((day) => {
        setPlanDay(day)
        setPlanFailed(false)
      })
      .catch(() => {
        // Falls back to the stored goals, and SAYS SO under the ring. A ring
        // silently drawn against a target that may be wrong is the kind of
        // wrong nobody reports, because nothing about it looks wrong.
        setPlanDay(null)
        setPlanFailed(true)
      })
    // Quick log is a shortcut, not content: if it fails to load the panel is
    // simply absent, the same way a failed trend leaves the chart out. Raising
    // an error banner for it would be louder than the feature is important.
    api.getMealTemplates().then(setTemplates).catch(() => setTemplates([]))
  }, [viewedDate])

  useEffect(() => {
    load()
  }, [load])

  const remove = async (id: number) => {
    try {
      await api.deleteMeal(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed — try again.')
      return
    } finally {
      setConfirmDelete(null)
    }
    load()
  }

  // Minted on demand rather than alongside every meal in the list: a code is
  // derived from a row, so there is nothing to cache and nothing to keep in
  // sync when the row changes.
  const showCode = async (label: string, mint: () => Promise<{ code: string }>) => {
    setShareError(null)
    try {
      setShareCode({ label, code: (await mint()).code })
    } catch (err) {
      setShareCode(null)
      setShareError(err instanceof Error ? err.message : 'Could not make a code.')
    }
  }

  const consumed = {
    calories: meals.reduce((sum, meal) => sum + meal.calories, 0),
    protein: meals.reduce((sum, meal) => sum + meal.protein, 0),
    carbs: meals.reduce((sum, meal) => sum + (meal.carbs ?? 0), 0),
    fat: meals.reduce((sum, meal) => sum + (meal.fat ?? 0), 0),
  }

  // Checked at render rather than trusted from state. Two day-switches in
  // quick succession can land their responses out of order, and the late one
  // would otherwise draw this day's rings against the other day's target --
  // silently, since a ring gives no sign which day it was told about. The
  // stale value is dropped instead, and the goals fall back for the moment it
  // takes the right response to arrive.
  const dayPlan = planDay?.date === viewedDate ? planDay : null
  const goals = dayPlan ?? settings

  // Ordered by what this device last logged, so the six that show are the six
  // being used rather than the six most recently created. Read once per mount:
  // tapping one writes to storage and navigates away, and the new order is
  // there when the dashboard comes back.
  const ordered = useMemo(
    () => (user ? byRecentUse(templates, user.id) : templates),
    [templates, user],
  )

  // Collapsed shows the first six; expanded shows everything, filtered.
  // Collapsing clears the filter too, so reopening never presents a list
  // mysteriously shorter than the count printed on the button that opened it.
  const shownTemplates = useMemo(() => {
    if (!browsingTemplates) return ordered.slice(0, QUICK_LOG_VISIBLE)
    const needle = templateFilter.trim().toLowerCase()
    if (needle === '') return ordered
    return ordered.filter((template) => template.name.toLowerCase().includes(needle))
  }, [ordered, browsingTemplates, templateFilter])

  const toggleBrowsing = () => {
    setTemplateFilter('')
    setBrowsingTemplates((open) => !open)
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewedDate((d) => addDays(d, -1))}
              className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-2 text-slate-300 hover:bg-slate-800"
              title="Previous day"
              aria-label="Previous day"
            >
              ◀
            </button>
            <button
              onClick={() => setViewedDate((d) => addDays(d, 1))}
              disabled={isToday}
              className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-2 text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
              title="Next day"
              aria-label="Next day"
            >
              ▶
            </button>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">
                {isToday
                  ? 'Today'
                  : parseIsoDate(viewedDate).toLocaleDateString(undefined, { weekday: 'long' })}
              </h1>
              {!isToday && (
                <button
                  onClick={() => setViewedDate(localIsoDate())}
                  className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs text-slate-300 hover:bg-slate-700"
                >
                  Jump to today
                </button>
              )}
            </div>
            <input
              type="date"
              value={viewedDate}
              max={realToday}
              onChange={(e) => e.target.value && setViewedDate(e.target.value)}
              className="mt-1 rounded border border-slate-800 bg-slate-900 px-2 py-1 text-base sm:text-sm text-slate-400"
              aria-label="Pick a date"
            />
          </div>
        </div>
        <Link
          to={`/log?date=${viewedDate}`}
          className={`${primaryButtonClass} px-5 py-2.5`}
        >
          + Log a meal
        </Link>
      </header>

      {settings && goals && (
        <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MacroRing
            label="Calories"
            value={consumed.calories}
            goal={goals.calorie_goal}
            unit="kcal"
            color={macroHues.calories}
            caption={planCaption(dayPlan, planFailed)}
          />
          <MacroRing
            label="Protein"
            value={consumed.protein}
            goal={goals.protein_goal}
            unit="g"
            color={macroHues.protein}
          />
          {settings.track_carbs && (
            <MacroRing
              label="Carbs"
              value={consumed.carbs}
              goal={goals.carbs_goal}
              unit="g"
              color={macroHues.carbs}
            />
          )}
          {settings.track_fat && (
            <MacroRing
              label="Fat"
              value={consumed.fat}
              goal={goals.fat_goal}
              unit="g"
              color={macroHues.fat}
            />
          )}
        </section>
      )}

      {/* The entire discovery path for calorie planning, and deliberately a
          plain standing link rather than something that appears when you go
          over. A link that shows up only after an overage is still the app
          offering, just wearing a quieter coat -- and being asked "shall we cut
          the next four days?" every time you overshoot is the thing that turns
          a planning tool into a loop. This is here whether the day went well or
          badly, and it waits to be looked for. */}
      {settings && (
        <div className="-mt-2 text-right">
          <Link
            to={`/settings/goals?plan=${viewedDate}`}
            className="text-xs text-ink-faint hover:text-slate-300"
          >
            Plan a bigger day, or spread one you already had →
          </Link>
        </div>
      )}

      {/* Hidden entirely until there is something to log. The entry point is
          the "Save as template" button on Log Meal; a permanent empty-state
          card would spend prime screen space explaining a feature once.

          ABOVE the tracker grid, which is where this comment always claimed it
          was while the code put it below. On a phone, re-logging yesterday's
          breakfast belongs above three progress bars.

          A grid of plain buttons, not the segmented pill this used to be. That
          pill welded a share and a delete onto the thing you were trying to
          tap: the delete was px-2 text-xs, far under the 44px minimum, and
          confirming it grew the pill to four buttons in place and reflowed the
          whole flex-wrap row. Management moved to Settings -> Library, where
          you are reading a list rather than aiming at one. A fixed grid never
          reflows and every cell is a full-width target.

          Six, then the rest unfold in place. Unfolding rather than a modal is
          deliberate: the two modals this app already has lack Escape, a focus
          trap and scroll lock, and a third would deepen a debt that the
          primitive migration may never be run to pay off. The whole list is
          already in memory, so the filter costs no round trip. */}
      {templates.length > 0 && (
        <Card as="section">
          <h2 className="mb-3 font-semibold">Quick log</h2>

          {browsingTemplates && (
            <TextInput
              value={templateFilter}
              onChange={(event) => setTemplateFilter(event.target.value)}
              placeholder="Filter by name…"
              aria-label="Filter saved meals"
              className="mb-3 w-full"
            />
          )}

          {shownTemplates.length === 0 ? (
            <p className="text-sm text-ink-faint">
              Nothing matches “{templateFilter.trim()}”.
            </p>
          ) : (
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {shownTemplates.map((template) => (
                <li key={template.id}>
                  {/* Carries the viewed date, not today's: a template tapped
                      while looking at yesterday must land on yesterday. */}
                  <Link
                    to={`/log?date=${viewedDate}`}
                    state={{ template }}
                    onClick={() => user && rememberTemplate(user.id, template.id)}
                    className="flex flex-col rounded-lg border border-slate-700 px-3 py-2.5 hover:border-emerald-500 hover:text-emerald-300"
                  >
                    <span className="truncate text-sm font-medium text-slate-200">
                      {template.name}
                    </span>
                    <span className="mt-0.5 truncate text-xs text-ink-faint">
                      {Math.round(template.calories)} kcal ·{' '}
                      {Math.round(template.protein)} g
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {templates.length > QUICK_LOG_VISIBLE && (
            <button
              onClick={toggleBrowsing}
              aria-expanded={browsingTemplates}
              className="mt-3 w-full rounded-lg px-3 py-2 text-center text-xs text-ink-faint hover:bg-slate-800 hover:text-slate-300"
            >
              {browsingTemplates
                ? 'Show fewer ▴'
                : `Browse all (${templates.length}) ▾`}
            </button>
          )}
        </Card>
      )}

      {/* The three daily trackers.

          One section holding a grid, not a stack of full-width cards — this is
          where steps and supplements landed, and three trackers each taking a
          full row would push the meal list off the first screen on a phone.
          Adding another is adding a child here.

          It sits below the rings because those are the primary targets, and
          below Quick log because that is a tap you came here to make while
          these three are a glance.

          NOTE this block used to describe itself as "the daily quick-logs",
          one word away from the Quick log section directly above it — two
          different features with nearly the same name in one file. These are
          trackers; Quick log is meals.

          `viewedDate`, not today: the header's ◀ ▶ already move the whole page
          through time, and a tracker that ignored them would be the only part
          of this screen showing a different day from the rest. */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <WaterCard date={viewedDate} />
        <StepsCard date={viewedDate} />
        {/* Renders nothing until there is a supplement to tick, so the grid is
            two cards wide for an account that has not set any up. The entry
            point is Settings; a permanent empty card would spend prime space
            explaining a feature once. */}
        <SupplementsCard date={viewedDate} />
      </section>

      {/* Directly above the meal list, which is now its only trigger on this
          page: template sharing moved to Settings -> Library along with the
          rest of template management. */}
      {shareError && (
        <Card as="p" tone="error" pad="sm" className="text-sm">
          {shareError}
        </Card>
      )}
      {shareCode && (
        <ShareCodePanel
          label={shareCode.label}
          code={shareCode.code}
          onClose={() => setShareCode(null)}
        />
      )}

      <section className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <h2 className="mb-3 font-semibold">
            {isToday
              ? "Today's meals"
              : `Meals · ${parseIsoDate(viewedDate).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}`}
          </h2>
          {error && (
            <p className="mb-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
              {error}{' '}
              <button onClick={load} className="underline hover:text-rose-200">
                Retry
              </button>
            </p>
          )}
          {meals.length === 0 ? (
            !error && (
              <p className="py-6 text-center text-sm text-ink-faint">
                Nothing logged yet — <Link to={`/log?date=${viewedDate}`} className="text-emerald-400 hover:underline">log your first meal</Link>.
              </p>
            )
          ) : (
            <ul className="divide-y divide-slate-800">
              {meals.map((meal) => (
                <li key={meal.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div>
                    <p className="text-sm font-medium">{meal.name}</p>
                    <p className="text-xs text-slate-400">
                      {Math.round(meal.calories)} kcal · {Math.round(meal.protein)} g protein
                      {settings?.track_carbs && meal.carbs != null && ` · ${Math.round(meal.carbs)} g carbs`}
                      {settings?.track_fat && meal.fat != null && ` · ${Math.round(meal.fat)} g fat`}
                    </p>
                  </div>
                  {confirmDelete === meal.id ? (
                    <span className="flex items-center gap-2 text-xs">
                      <button onClick={() => remove(meal.id)} className="rounded bg-rose-500/20 px-2 py-1 text-rose-300 hover:bg-rose-500/30">
                        Delete
                      </button>
                      <button onClick={() => setConfirmDelete(null)} className="rounded bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700">
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <span className="flex items-center gap-3">
                      <button
                        onClick={() =>
                          showCode(meal.name, () => api.shareMeal(meal.id))
                        }
                        className="text-xs text-ink-faint hover:text-emerald-400"
                        title="Copy this meal as a code"
                      >
                        📋
                      </button>
                      <Link
                        to="/log"
                        state={{ editMeal: meal }}
                        className="text-xs text-ink-faint hover:text-emerald-400"
                        title="Edit meal"
                      >
                        ✎
                      </Link>
                      <button
                        onClick={() => setConfirmDelete(meal.id)}
                        className="text-xs text-ink-faint hover:text-rose-400"
                        title="Delete meal"
                      >
                        ✕
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2">
          {/* "Previous", not "Last": the range ends yesterday. Today is already
              on this page in full — the rings and the meal list above — so
              leaving it out of the trend costs nothing and keeps the chart and
              the average below it telling the same story. */}
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 className="font-semibold">Previous 7 days</h2>
            {/* The review covers exactly this window, so the link belongs on
                the numbers it summarises rather than in a card of its own.
                Outside the `week &&` guard below on purpose: a week with
                nothing logged is precisely when "you logged no meals, so there
                is nothing to review yet" is worth reading. */}
            <Link to="/review" className="text-xs text-ink-muted underline hover:text-emerald-300">
              Weekly review →
            </Link>
          </div>
          {week && week.days.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={week.days} margin={chartMargin}>
                <defs>
                  <linearGradient id="calGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={macroHues.calories} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={macroHues.calories} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={axisTick}
                  tickFormatter={shortDate}
                  stroke={axisStroke}
                />
                <YAxis tick={axisTick} stroke={axisStroke} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                />
                <Area
                  type="monotone"
                  dataKey="calories"
                  stroke={macroHues.calories}
                  strokeWidth={2}
                  fill="url(#calGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-6 text-center text-sm text-ink-faint">
              Nothing logged in the seven days before today.
            </p>
          )}
          {week && week.days.length > 0 && (
            <p className="mt-2 text-xs text-slate-400">
              Avg {Math.round(week.averages.calories)} kcal ·{' '}
              {Math.round(week.averages.protein)} g protein per day
              {/* The denominator, in the open. Averaging over logged days is
                  what stops a forgotten day reading as a fasting day, but it
                  does mean the figure is built from fewer days than the card's
                  title suggests — so say how many. */}
              <span className="text-ink-faint">
                {' '}
                over {week.logged_days} logged day
                {week.logged_days === 1 ? '' : 's'}, excluding today
              </span>
            </p>
          )}
        </Card>
      </section>
    </div>
  )
}
