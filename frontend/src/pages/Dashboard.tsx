import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import MacroRing from '../components/MacroRing'
import { localIsoDate } from '../lib/dates'
import type { AnalyticsSummary, Meal, Settings } from '../types'

export default function Dashboard() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [meals, setMeals] = useState<Meal[]>([])
  const [week, setWeek] = useState<AnalyticsSummary | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [today, setToday] = useState(localIsoDate)

  // Refresh the date when the tab regains focus, so a session left open past
  // midnight doesn't keep showing yesterday. Same-string updates are no-ops.
  useEffect(() => {
    const refresh = () => setToday(localIsoDate())
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])

  const load = useCallback(() => {
    const weekAgo = new Date()
    weekAgo.setDate(weekAgo.getDate() - 6)
    setError(null)
    // A failed load must not masquerade as an empty day.
    api.getMeals(today).then(setMeals).catch(() => {
      setMeals([])
      setError("Couldn't load your meals — check your connection and try again.")
    })
    api.getAnalytics(localIsoDate(weekAgo), today).then(setWeek).catch(() => setWeek(null))
  }, [today])

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => null)
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

  const consumed = {
    calories: meals.reduce((sum, meal) => sum + meal.calories, 0),
    protein: meals.reduce((sum, meal) => sum + meal.protein, 0),
    carbs: meals.reduce((sum, meal) => sum + (meal.carbs ?? 0), 0),
    fat: meals.reduce((sum, meal) => sum + (meal.fat ?? 0), 0),
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Today</h2>
          <p className="text-sm text-slate-400">
            {new Date().toLocaleDateString(undefined, {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })}
          </p>
        </div>
        <Link
          to="/log"
          className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
        >
          + Log a meal
        </Link>
      </header>

      {settings && (
        <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MacroRing
            label="Calories"
            value={consumed.calories}
            goal={settings.calorie_goal}
            unit="kcal"
            color="#f59e0b"
          />
          <MacroRing
            label="Protein"
            value={consumed.protein}
            goal={settings.protein_goal}
            unit="g"
            color="#34d399"
          />
          {settings.track_carbs && (
            <MacroRing
              label="Carbs"
              value={consumed.carbs}
              goal={settings.carbs_goal}
              unit="g"
              color="#38bdf8"
            />
          )}
          {settings.track_fat && (
            <MacroRing
              label="Fat"
              value={consumed.fat}
              goal={settings.fat_goal}
              unit="g"
              color="#fb7185"
            />
          )}
        </section>
      )}

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 lg:col-span-3">
          <h3 className="mb-3 font-semibold">Today's meals</h3>
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
              <p className="py-6 text-center text-sm text-slate-500">
                Nothing logged yet — <Link to="/log" className="text-emerald-400 hover:underline">log your first meal</Link>.
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
                      <Link
                        to="/log"
                        state={{ editMeal: meal }}
                        className="text-xs text-slate-500 hover:text-emerald-400"
                        title="Edit meal"
                      >
                        ✎
                      </Link>
                      <button
                        onClick={() => setConfirmDelete(meal.id)}
                        className="text-xs text-slate-500 hover:text-rose-400"
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
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 lg:col-span-2">
          <h3 className="mb-3 font-semibold">Last 7 days</h3>
          {week && week.days.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={week.days} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="calGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={(value: string) => value.slice(5)}
                  stroke="#334155"
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="#334155" />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#e2e8f0' }}
                />
                <Area
                  type="monotone"
                  dataKey="calories"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  fill="url(#calGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-6 text-center text-sm text-slate-500">No data yet this week.</p>
          )}
          {week && (
            <p className="mt-2 text-xs text-slate-400">
              Avg {Math.round(week.averages.calories)} kcal · {Math.round(week.averages.protein)} g protein per day
            </p>
          )}
        </div>
      </section>
    </div>
  )
}
