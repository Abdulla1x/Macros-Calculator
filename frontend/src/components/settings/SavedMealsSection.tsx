import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import ShareCodePanel from '../ShareCodePanel'
import type { MealTemplate } from '../../types'
import Card from '../ui/Card'
import TextInput from '../ui/TextInput'
import ShowAllToggle, { COLLAPSED_ROWS } from './ShowAllToggle'

/** The saved meals behind Quick log: see them, share one, remove one.
 *
 * This is where template management moved to when the dashboard's Quick log
 * became a grid of plain buttons. On the dashboard a template is a thing you
 * tap, and a delete control sitting beside it -- under the minimum touch target,
 * and reflowing the whole row when it expanded to confirm -- was a hazard next
 * to the one control you actually wanted. Here you are reading a list, which is
 * where a destructive action belongs.
 *
 * It sits beside the food library because both answer the same question: what
 * has the app remembered on my behalf, and how do I correct it. Like the food
 * library, everything here writes straight to the server.
 */
export default function SavedMealsSection() {
  const [items, setItems] = useState<MealTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [shareCode, setShareCode] = useState<{ label: string; code: string } | null>(null)
  const [expanded, setExpanded] = useState(false)

  const load = () => {
    setLoading(true)
    api
      .getMealTemplates()
      .then((next) => {
        setItems(next)
        setError('')
      })
      // An empty list and a failed fetch render identically, and one of them
      // means "nothing saved yet" while the other means "try again".
      .catch(() => setError("Couldn't load your saved meals."))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  // The whole list is already in memory, so filtering here costs no round trip
  // per keystroke -- the idiom FoodLibrarySection established next door.
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (needle === '') return items
    return items.filter((meal) => meal.name.toLowerCase().includes(needle))
  }, [items, filter])

  // Capped after filtering, the same way FoodLibrarySection does it next door.
  // This section stacks under that one, so an uncapped list here would put the
  // page's own footer back out of reach even once the library above is short.
  const visible = expanded ? shown : shown.slice(0, COLLAPSED_ROWS)

  const remove = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteMealTemplate(id)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed — try again.')
    } finally {
      setBusy(false)
      setConfirmDelete(null)
    }
  }

  // Minted on demand rather than alongside every row: a code is derived from a
  // template, so there is nothing to cache and nothing to keep in sync when the
  // template changes.
  const showCode = async (meal: MealTemplate) => {
    setBusy(true)
    try {
      setShareCode({ label: meal.name, code: (await api.shareMealTemplate(meal.id)).code })
      setError('')
    } catch (err) {
      setShareCode(null)
      setError(err instanceof Error ? err.message : 'Could not make a code.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card as="section">
      <h2 className="mb-1 font-semibold">🍽️ Saved meals</h2>
      <p className="mb-4 text-sm text-slate-400">
        The one-tap entries in <strong className="text-slate-300">Quick log</strong> on
        your dashboard. They are saved when you tick “Save as template” while
        logging a meal. Tapping one there logs it again; this is where you share
        or remove one. Changes here save straight away.
      </p>

      {error && (
        <p className="mb-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error}{' '}
          <button onClick={load} className="underline hover:text-rose-200">
            Retry
          </button>
        </p>
      )}

      {items.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <TextInput
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by name…"
            aria-label="Filter saved meals"
            className="min-w-0 flex-1"
          />
          <span className="text-xs text-slate-400">
            {items.length} meal{items.length === 1 ? '' : 's'}
            {filter.trim() !== '' && ` · ${shown.length} matching`}
          </span>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400">
          Nothing saved yet. Tick “Save as template” while logging a meal and it
          will show up here, and in Quick log on your dashboard.
        </p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing matches “{filter.trim()}”.</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {visible.map((meal) => (
            <li
              key={meal.id}
              className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="text-slate-200">
                  <span className="font-medium">{meal.name}</span>
                  <span className="ml-2 text-xs text-slate-400">
                    {Math.round(meal.calories)} kcal · {Math.round(meal.protein)} g protein
                  </span>
                </span>
                <span className="ml-auto flex items-center gap-2 text-xs">
                  <button
                    onClick={() => showCode(meal)}
                    disabled={busy}
                    className="text-slate-400 hover:text-emerald-300 disabled:opacity-40"
                  >
                    Share
                  </button>
                  {confirmDelete === meal.id ? (
                    <>
                      <button
                        onClick={() => remove(meal.id)}
                        disabled={busy}
                        className="rounded border border-rose-500/50 bg-rose-500/10 px-2 py-0.5 text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
                      >
                        Delete for good
                      </button>
                      <button
                        onClick={() => setConfirmDelete(null)}
                        className="text-slate-400 hover:text-slate-200"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setConfirmDelete(meal.id)}
                      disabled={busy}
                      aria-label={`Delete the ${meal.name} template`}
                      className="text-slate-400 hover:text-rose-400 disabled:opacity-40"
                    >
                      Delete
                    </button>
                  )}
                </span>
                {confirmDelete === meal.id && (
                  <p className="w-full text-xs text-slate-400">
                    This only removes the shortcut. Meals you already logged from
                    it keep their numbers.
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <ShowAllToggle
        total={shown.length}
        cap={COLLAPSED_ROWS}
        expanded={expanded}
        onToggle={() => {
          setExpanded((current) => !current)
          // As in the food library above: a confirmation does not survive being
          // hidden.
          setConfirmDelete(null)
        }}
        noun="meal"
      />

      {shareCode && (
        <ShareCodePanel
          label={shareCode.label}
          code={shareCode.code}
          onClose={() => setShareCode(null)}
        />
      )}
    </Card>
  )
}
