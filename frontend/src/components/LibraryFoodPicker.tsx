import { useMemo, useState } from 'react'
import type { Food } from '../types'
import TextInput, { inputSurfaceClass } from './ui/TextInput'

interface Props {
  /** The whole library. Fetched and owned by MealAnalyzer, which also hands it
   *  to LogMeal on apply, so there is exactly one copy and one request. */
  foods: Food[]
  attached: Food[]
  max: number
  onAttach: (food: Food) => void
  onDetach: (foodId: number) => void
}

/**
 * Pick saved foods to send to the AI as exact facts.
 *
 * The whole library is listed and narrowed by typing, rather than searched a
 * query at a time the way FoodAutocomplete does below on the same page. That is
 * a deliberate difference, not an inconsistency: filling in an ingredient you
 * are already naming is searching, while deciding which of your foods are on
 * this plate is browsing, and an empty search box shows nothing to browse. It
 * is the idiom Quick log's "Browse all" and the Settings food library already
 * use, and the filtering costs no round trips because the list is in memory.
 *
 * Closed by default: on a phone an always-open list would push the Analyze
 * button off screen. The attached chips stay visible either way, so what is
 * going to be sent is readable without opening anything.
 */
export default function LibraryFoodPicker({
  foods,
  attached,
  max,
  onAttach,
  onDetach,
}: Props) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const full = attached.length >= max

  // Already-attached foods drop out of the list rather than showing as disabled
  // rows: the chips above are where they are, and a list that keeps them is
  // mostly a list of things you cannot do.
  const visible = useMemo(() => {
    const query = filter.trim().toLowerCase()
    const taken = new Set(attached.map((food) => food.id))
    return foods.filter(
      (food) =>
        !taken.has(food.id) &&
        (query === '' || food.name.toLowerCase().includes(query)),
    )
  }, [foods, attached, filter])

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="rounded-control border border-line-strong px-3 py-2 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
      >
        🥣 Use foods from your library
        {attached.length > 0 && ` (${attached.length})`} {open ? '▲' : '▼'}
      </button>
      <p className="mt-1 text-xs text-ink-faint">
        Attach a saved food and the AI works out how much you ate instead of
        guessing its macros.
      </p>

      {attached.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {attached.map((food) => (
            <li key={food.id}>
              <button
                type="button"
                onClick={() => onDetach(food.id)}
                aria-label={`Remove ${food.name}`}
                className="rounded-full border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300 hover:border-rose-500 hover:text-rose-300"
              >
                {food.name} ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className={`mt-2 overflow-hidden ${inputSurfaceClass}`}>
          <div className="p-2">
            <TextInput
              type="text"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter your library…"
              className="w-full"
            />
          </div>

          {foods.length === 0 ? (
            <p className="border-t border-line-strong px-3 py-2 text-sm text-slate-400">
              Nothing saved yet. Foods you tick “save to my library” on while
              logging show up here.
            </p>
          ) : visible.length === 0 ? (
            <p className="border-t border-line-strong px-3 py-2 text-sm text-slate-400">
              {filter.trim()
                ? `Nothing in your library matches “${filter.trim()}”.`
                : 'Everything in your library is already attached.'}
            </p>
          ) : (
            <ul className="max-h-56 overflow-y-auto border-t border-line-strong">
              {visible.map((food) => (
                <li key={food.id}>
                  <button
                    type="button"
                    onClick={() => onAttach(food)}
                    disabled={full}
                    className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-700 disabled:opacity-50 disabled:hover:bg-transparent"
                  >
                    <span className="font-medium">{food.name}</span>
                    <span className="shrink-0 text-xs text-slate-400">
                      {food.calories} kcal · {food.protein} g P / {food.serving_size} g
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {full && (
            <p className="border-t border-line-strong px-3 py-2 text-xs text-amber-300">
              That’s the limit — {max} saved foods per analysis.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
