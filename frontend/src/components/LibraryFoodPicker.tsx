import { useMemo, useState } from 'react'
import type { Food } from '../types'
import { FIELD } from '@/ui/field'
import { CloseIcon, SavedFoodsIcon } from '@/ui/icons'

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
 * is the idiom Saved meals's "Browse all" and the Settings food library already
 * use, and the filtering costs no round trips because the list is in memory.
 *
 * Closed by default: on a phone an always-open list would push the Estimate
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
    <div className="grid gap-2">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex min-h-11 items-center gap-2 justify-self-start rounded-control border-[1.5px] border-rule px-3 text-[14.5px] font-semibold hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        <SavedFoodsIcon size={18} aria-hidden />
        Use my saved foods
        {attached.length > 0 && <span className="font-normal text-ink-2 tabular-nums">{attached.length}</span>}
        <span aria-hidden="true" className="text-ink-2">
          {open ? '▴' : '▾'}
        </span>
      </button>
      <p className="text-small text-ink-2">
        Your saved foods count as facts: the AI only judges how much you ate.
      </p>

      {attached.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {attached.map((food) => (
            <li key={food.id}>
              <button
                type="button"
                onClick={() => onDetach(food.id)}
                aria-label={`Remove ${food.name}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-control border-[1.5px] border-ink bg-ink px-3 text-[13.5px] font-semibold text-ground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
              >
                {food.name}
                <CloseIcon size={14} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="overflow-hidden rounded-control border-[1.5px] border-rule bg-field">
          <div className="p-2">
            <input
              type="text"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter your saved foods…"
              aria-label="Filter your saved foods"
              className={FIELD}
            />
          </div>

          {foods.length === 0 ? (
            <p className="border-t border-rule px-3 py-2 text-small text-ink-2">
              Nothing saved yet. Foods you save while logging show up here.
            </p>
          ) : visible.length === 0 ? (
            <p className="border-t border-rule px-3 py-2 text-small text-ink-2">
              {filter.trim()
                ? `Nothing saved matches “${filter.trim()}”.`
                : 'Every saved food is already attached.'}
            </p>
          ) : (
            <ul className="max-h-56 divide-y divide-rule overflow-y-auto border-t border-rule">
              {visible.map((food) => (
                <li key={food.id}>
                  <button
                    type="button"
                    onClick={() => onAttach(food)}
                    disabled={full}
                    className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-body hover:bg-ink/5 disabled:opacity-45 disabled:hover:bg-transparent"
                  >
                    <span className="min-w-0 truncate">{food.name}</span>
                    <span className="shrink-0 text-small text-ink-2 tabular-nums">
                      {food.calories} kcal · {food.protein} g P / {food.serving_size} g
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {full && (
            <p className="border-t border-rule px-3 py-2 text-small">
              That’s the limit: {max} saved foods per estimate.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
