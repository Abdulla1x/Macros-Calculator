import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { daysBetween, localIsoDate, parseIsoDate } from '../../lib/dates'
import { byRecentUse, rememberTemplate } from '../../lib/recentTemplates'
import type { Meal, MealTemplate } from '../../types'
import { useLiveMessage } from '../../hooks/useLiveMessage'
import { FIELD } from '@/ui/field'
import { SearchIcon } from '@/ui/icons'
import { logDate } from './logPanelUrl'
import { useLogPanel } from './useLogPanel'

// How many of each list show at first (owner, after the P40 test: six each
// made the panel long, and a search reaches the rest). Three covers the meals
// logged most often without pushing "Enter it by hand" off the first screen.
const VISIBLE = 3
// Recent grows by this much per "Show more", up to RECENT_MAX: the server's
// ceiling for one listing (`limit` le=50 on /api/meals/recent), already one row
// per name, so fifty names is roughly seven weeks of a varied diet.
const RECENT_STEP = 10
const RECENT_MAX = 50

const ROW =
  'flex min-h-[52px] w-full items-center gap-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

const MORE =
  'min-h-11 justify-self-start px-1 text-small font-semibold text-action underline underline-offset-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

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

function Section({ label, count, children }: { label: string; count?: string; children: React.ReactNode }) {
  return (
    <section className="grid grid-cols-[minmax(0,1fr)]">
      <h3 className="flex items-center justify-between pb-1 text-field-label text-ink-2">
        <span>{label}</span>
        {count !== undefined && <span className="tabular-nums">{count}</span>}
      </h3>
      {children}
    </section>
  )
}

const matches = (name: string, needle: string) => name.toLowerCase().includes(needle)

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

/** Saved meals and recent meals in the Log panel, under the AI box (overhaul
 *  0a: AI is about half of meals, and saved and recent meals carry most of the
 *  rest, so they sit directly under it), with one search over both.
 *
 *  Saved meals used to be a folded card on Today, above the day's meals (UA-3):
 *  logging inputs on the page meant for reading the day. They are ordered by
 *  what this device last logged, so the first rows are the ones in use.
 *
 *  Recent meals are the newest meal under each name: the one eaten on Tuesday
 *  that nobody thought to save. Not merged with saved meals, because they answer
 *  different questions ("I eat this often" vs "I ate this recently"). A copy is
 *  a new meal on the panel's day; the original stays where it is.
 *
 *  Both lists start at three rows. The search is always there rather than
 *  behind "Show all" (owner, P40 test), and reaches every saved meal and the
 *  fifty most recent names, including the rows not on screen. Each list is
 *  hidden while it has nothing, and the whole block while both are empty. */
export default function MealShortcuts() {
  const { user } = useAuth()
  const { search } = useLocation()
  const { open } = useLogPanel()
  const today = localIsoDate()
  const date = logDate(search) ?? today

  const [templates, setTemplates] = useState<MealTemplate[]>([])
  const [recent, setRecent] = useState<Meal[]>([])
  const [query, setQuery] = useState('')
  const [allSaved, setAllSaved] = useState(false)
  const [recentShown, setRecentShown] = useState(VISIBLE)

  // Shortcuts, not content: a list that fails to load is simply absent, which
  // is quieter than an error for something this optional.
  useEffect(() => {
    api.getMealTemplates().then(setTemplates).catch(() => setTemplates([]))
  }, [])
  // All fifty at once, so "Show more" and the search need no further request:
  // the server has already reduced the history to one row per name, so this is
  // a few kilobytes. Relative to the panel's day, so logging for yesterday
  // offers what came before yesterday.
  useEffect(() => {
    api
      .getRecentMeals(RECENT_MAX, date)
      .then(setRecent)
      .catch(() => setRecent([]))
  }, [date])

  const ordered = useMemo(() => (user ? byRecentUse(templates, user.id) : templates), [templates, user])
  const needle = query.trim().toLowerCase()
  const savedShown = needle
    ? ordered.filter((template) => matches(template.name, needle))
    : allSaved
      ? ordered
      : ordered.slice(0, VISIBLE)
  const recentList = needle ? recent.filter((meal) => matches(meal.name, needle)) : recent.slice(0, recentShown)

  // Said once the typing settles, not per keystroke: a screen reader user
  // hears how many rows the search left, which sighted users see at a glance.
  const [said, setSaid] = useState<string | null>(null)
  useEffect(() => {
    if (!needle) return setSaid(null)
    const timer = window.setTimeout(() => {
      const found = savedShown.length + recentList.length
      setSaid(found === 0 ? `No meals match "${query.trim()}".` : `${found} meal${found === 1 ? '' : 's'} match.`)
    }, 500)
    return () => window.clearTimeout(timer)
  }, [needle, query, savedShown.length, recentList.length])
  useLiveMessage(said)

  if (templates.length === 0 && recent.length === 0) return null
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <label className="relative grid">
        <span className="sr-only">Search saved and recent meals</span>
        <SearchIcon size={18} aria-hidden="true" className="pointer-events-none absolute top-[13px] left-3 text-ink-2" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search saved and recent meals"
          autoComplete="off"
          enterKeyHint="search"
          className={`${FIELD} pl-9`}
        />
      </label>

      {templates.length > 0 && (
        <Section label="Saved meals" count={needle ? `${savedShown.length} of ${templates.length}` : `${templates.length}`}>
          {savedShown.length === 0 ? (
            <p className="py-2 text-small text-ink-2">No saved meal matches.</p>
          ) : (
            <ul className="divide-y divide-rule border-y border-rule">
              {savedShown.map((template) => (
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
          {!needle && templates.length > VISIBLE && (
            <button type="button" aria-expanded={allSaved} onClick={() => setAllSaved((now) => !now)} className={MORE}>
              {allSaved ? 'Show fewer' : `Show all ${templates.length}`}
            </button>
          )}
        </Section>
      )}

      {recent.length > 0 && (
        <Section label="Recent" count={needle ? `${recentList.length} found` : undefined}>
          {recentList.length === 0 ? (
            <p className="py-2 text-small text-ink-2">Nothing recent matches.</p>
          ) : (
            <ul className="divide-y divide-rule border-y border-rule">
              {recentList.map((meal) => (
                <MealRow
                  key={meal.id}
                  name={meal.name}
                  detail={`${dayLabel(meal.date, today)} · ${Math.round(meal.protein)} g protein`}
                  kcal={meal.calories}
                  onPick={() => open('hand', { state: { copyMeal: meal } })}
                />
              ))}
            </ul>
          )}
          {!needle &&
            (recentShown < recent.length ? (
              <button type="button" onClick={() => setRecentShown((now) => now + RECENT_STEP)} className={MORE}>
                Show more
              </button>
            ) : (
              recentShown > VISIBLE && (
                <button type="button" onClick={() => setRecentShown(VISIBLE)} className={MORE}>
                  Show fewer
                </button>
              )
            ))}
        </Section>
      )}
    </div>
  )
}
