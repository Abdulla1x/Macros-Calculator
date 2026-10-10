import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { daysBetween, localIsoDate, parseIsoDate } from '../../lib/dates'
import { byRecentUse, rememberTemplate } from '../../lib/recentTemplates'
import type { Meal, MealTemplate } from '../../types'
import TextInput from '../ui/TextInput'
import { logDate } from './logPanelUrl'
import { useLogPanel } from './useLogPanel'

// How many of each list show before "Show all". Six is what Today showed, and
// the server caps a template listing at 50 while nothing caps how many anyone
// can create, so an opened list still needs bounding.
const VISIBLE = 6

const ROW =
  'flex min-h-[52px] w-full items-center gap-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

/** "Tue", "Yesterday", "Sep 28": which day a recent meal's numbers are from.
 *  Shown because a recent row is the NEWEST meal under that name, and Monday's
 *  breakfast was not Tuesday's; the label is what stops that being a silent
 *  substitution. A weekday inside the last week, a date beyond it: "Tue" stops
 *  meaning anything once a second Tuesday has passed.
 *
 *  Deliberately NOT Admin.tsx's relativeDay, which looks like the same function
 *  and is not: it takes a timestamp and calls `new Date(iso)`, which reads a
 *  date-only string as UTC, the off-by-one-near-midnight bug parseIsoDate
 *  exists to avoid. A meal date is a calendar date. */
function dayLabel(iso: string, today: string): string {
  const days = daysBetween(iso, today)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return parseIsoDate(iso).toLocaleDateString(undefined, { weekday: 'short' })
  return parseIsoDate(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Section({ label, count, children }: { label: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="grid">
      <h3 className="flex items-center justify-between pb-1 text-field-label text-ink-2">
        <span>{label}</span>
        {count !== undefined && <span>{count}</span>}
      </h3>
      {children}
    </section>
  )
}

function MealRow({ name, detail, kcal, onPick }: { name: string; detail: string; kcal: number; onPick: () => void }) {
  return (
    <li>
      <button type="button" onClick={onPick} className={ROW}>
        <span className="grid min-w-0 flex-1">
          <span className="truncate text-body">{name}</span>
          <span className="truncate text-small text-ink-2">{detail}</span>
        </span>
        <span className="shrink-0 text-row-number tabular-nums">
          {Math.round(kcal).toLocaleString()}
          <span className="ml-1 text-small font-normal text-ink-2">kcal</span>
        </span>
      </button>
    </li>
  )
}

/** Saved meals (templates) in the Log panel, under the AI box (overhaul 0a:
 *  AI is about half of meals, and saved and recent meals carry most of the
 *  rest, so they sit directly under it). They used to be a folded card on
 *  Today, above the day's meals (UA-3): logging inputs on the page meant for
 *  reading the day. Ordered by what this device last logged, so the six shown
 *  are the six in use. Hidden when there are none. */
export function SavedMeals() {
  const { user } = useAuth()
  const { open } = useLogPanel()
  const [templates, setTemplates] = useState<MealTemplate[]>([])
  const [all, setAll] = useState(false)
  const [filter, setFilter] = useState('')

  // A shortcut, not content: if the list fails to load it is simply absent,
  // which is quieter than an error for something this optional.
  useEffect(() => {
    api.getMealTemplates().then(setTemplates).catch(() => setTemplates([]))
  }, [])

  const ordered = useMemo(() => (user ? byRecentUse(templates, user.id) : templates), [templates, user])
  const shown = useMemo(() => {
    if (!all) return ordered.slice(0, VISIBLE)
    const needle = filter.trim().toLowerCase()
    return needle ? ordered.filter((template) => template.name.toLowerCase().includes(needle)) : ordered
  }, [ordered, all, filter])

  if (templates.length === 0) return null
  return (
    <Section label="Saved meals" count={templates.length}>
      {all && (
        <TextInput
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter by name…"
          aria-label="Filter saved meals"
          className="mb-2 w-full"
        />
      )}
      {shown.length === 0 ? (
        <p className="py-3 text-small text-ink-2">Nothing matches “{filter.trim()}”.</p>
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {shown.map((template) => (
            <MealRow
              key={template.id}
              name={template.name}
              detail={`${Math.round(template.protein)} g protein`}
              kcal={template.calories}
              onPick={() => {
                if (user) rememberTemplate(user.id, template.id)
                // Opens the form filled in, so the portion can change before
                // saving. The panel's day travels with it in the address.
                open('hand', { state: { template } })
              }}
            />
          ))}
        </ul>
      )}
      {templates.length > VISIBLE && (
        <button
          type="button"
          aria-expanded={all}
          onClick={() => {
            setFilter('')
            setAll((current) => !current)
          }}
          className="min-h-11 justify-self-start px-1 text-small font-semibold text-action underline underline-offset-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
        >
          {all ? 'Show fewer' : `Show all ${templates.length}`}
        </button>
      )}
    </Section>
  )
}

/** Meals logged recently, once per name, newest first: the meal eaten on
 *  Tuesday that nobody thought to save. Not merged with saved meals, because
 *  they answer different questions ("I eat this often" vs "I ate this
 *  recently"). A copy is a new meal on the panel's day; the original stays
 *  where it is. Hidden when there are none. */
export function RecentMeals() {
  const { search } = useLocation()
  const { open } = useLogPanel()
  const [recent, setRecent] = useState<Meal[]>([])
  const today = localIsoDate()
  const date = logDate(search) ?? today

  // Asked for by count: the server has already reduced the history to one row
  // per name, so the list is short by construction. Relative to the panel's
  // day, so logging for yesterday offers what came before yesterday.
  useEffect(() => {
    api
      .getRecentMeals(VISIBLE, date)
      .then(setRecent)
      .catch(() => setRecent([]))
  }, [date])

  if (recent.length === 0) return null
  return (
    <Section label="Recent">
      <ul className="divide-y divide-rule border-y border-rule">
        {recent.map((meal) => (
          <MealRow
            key={meal.id}
            name={meal.name}
            detail={`${dayLabel(meal.date, today)} · ${Math.round(meal.protein)} g protein`}
            kcal={meal.calories}
            onPick={() => open('hand', { state: { copyMeal: meal } })}
          />
        ))}
      </ul>
    </Section>
  )
}
