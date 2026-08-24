import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { MAX_FOOD_NAME, validateFood } from '../lib/limits'
import type { Food, FoodCreate } from '../types'

/** The saved-food library: see it, correct it, rename it, delete it.
 *
 * In its own file rather than inside Settings.tsx, which is where the other
 * four sections live. Deliberate: this is the largest of them -- a list that
 * grows on its own, a filter, an inline form and a delete confirmation -- and
 * Settings.tsx is already the biggest file in the frontend.
 *
 * Why the section exists at all: FoodAutocomplete saves every Open Food Facts
 * pick into the library without asking, and LogMeal saves every ingredient the
 * user ticks. Until now nothing displayed the result, so a wrong serving size
 * cached once kept autocompleting into every future meal with no way to reach
 * it.
 */

interface Draft {
  name: string
  servingSize: string
  calories: string
  protein: string
  carbs: string
  fat: string
}

/** 100 g as the default serving, because that is what Open Food Facts reports
 *  against and what most packaging prints. A blank would only be retyped. */
const emptyDraft = (): Draft => ({
  name: '',
  servingSize: '100',
  calories: '',
  protein: '',
  carbs: '',
  fat: '',
})

const draftFrom = (food: Food): Draft => ({
  name: food.name,
  servingSize: String(food.serving_size),
  calories: String(food.calories),
  protein: String(food.protein),
  carbs: food.carbs == null ? '' : String(food.carbs),
  fat: food.fat == null ? '' : String(food.fat),
})

// The same parse LogMeal and Settings use. Number('') is 0, and for carbs and
// fat a blank box means "not recorded", which is a different claim from zero.
const num = (value: string) => {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const macroSummary = (food: Food) =>
  `${food.calories} kcal · ${food.protein} g protein / ${food.serving_size} g`

export default function FoodLibrarySection({
  onRejected,
}: {
  onRejected: (message: string) => void
}) {
  const [items, setItems] = useState<Food[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')

  const load = () => {
    setLoading(true)
    api
      .getFoods()
      .then((next) => {
        setItems(next)
        setError('')
      })
      // An empty library and a failed fetch render identically, and one of them
      // means "nothing saved yet" while the other means "try again".
      .catch(() => setError("Couldn't load your food library."))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  // Filtered here rather than through /api/foods/search: that endpoint caps at
  // 10 and ranks for a dropdown, which is right for autocomplete and wrong for
  // an editor, where the point is to see everything you have. The whole library
  // is already in memory, so this also costs no round-trip per keystroke.
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (needle === '') return items
    return items.filter((food) => food.name.toLowerCase().includes(needle))
  }, [items, filter])

  // Opening or abandoning a form clears the last failure with it: a refusal
  // like "you already have a food called X" answers the attempt that caused it,
  // and leaving it up once that attempt is gone reads as a standing problem.
  const startAdd = () => {
    setError('')
    setDraft(emptyDraft())
    setEditing('new')
  }

  const startEdit = (food: Food) => {
    setError('')
    setDraft(draftFrom(food))
    setEditing(food.id)
  }

  const cancelEdit = () => {
    setError('')
    setEditing(null)
  }

  const save = async () => {
    const servingSize = num(draft.servingSize)
    const calories = num(draft.calories)
    const protein = num(draft.protein)
    const carbs = num(draft.carbs)
    const fat = num(draft.fat)

    const problem = validateFood(draft.name, servingSize, calories, protein, carbs, fat)
    if (problem) {
      onRejected(problem)
      return
    }

    const existing =
      typeof editing === 'number' ? items.find((food) => food.id === editing) : undefined

    const body: FoodCreate = {
      name: draft.name.trim(),
      // Non-null by the validator above, which refuses null for all three.
      serving_size: servingSize as number,
      calories: calories as number,
      protein: protein as number,
      carbs,
      fat,
      // Sent because FoodCreate carries the field, but the server decides the
      // real answer on an edit: correcting a number makes the row yours, a
      // rename leaves the badge alone. Passing the current value keeps this
      // from looking like a claim.
      source: existing?.source ?? 'user',
    }

    setBusy(true)
    try {
      if (editing === 'new') await api.saveFood(body)
      else if (typeof editing === 'number') await api.updateFood(editing, body)
      setEditing(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteFood(id)
      setConfirmDelete(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 font-semibold">🥫 Food library</h3>
      <p className="mb-4 text-sm text-slate-400">
        The foods autocomplete offers you when you log a meal. Things land here
        on their own:{' '}
        <strong className="text-slate-300">
          every Open Food Facts result you pick is saved here automatically
        </strong>
        , along with anything you ticked “save to library” on. This is where you
        correct one that is wrong. Changes here save straight away — the Save
        button below is for the settings above it.
      </p>
      <p className="mb-4 text-sm text-slate-400">
        Editing a food changes what gets filled in{' '}
        <strong className="text-slate-300">next</strong> time.{' '}
        <strong className="text-slate-300">
          Meals you have already logged keep the numbers they were saved with
        </strong>{' '}
        — a meal records its own macros, so nothing here rewrites your history.
      </p>

      {items.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by name…"
            aria-label="Filter food library"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
          />
          <span className="text-xs text-slate-400">
            {items.length} food{items.length === 1 ? '' : 's'}
            {filter.trim() !== '' && ` · ${shown.length} shown`}
          </span>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400">
          Nothing saved yet. Pick a food from Open Food Facts while logging a
          meal, or tick “save to library” on one you typed yourself, and it will
          show up here.
        </p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing matches “{filter.trim()}”.</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {shown.map((food) => (
            <li
              key={food.id}
              className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
            >
              {editing === food.id ? (
                <FoodForm
                  draft={draft}
                  setDraft={setDraft}
                  onSave={save}
                  onCancel={cancelEdit}
                  busy={busy}
                />
              ) : (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  <span className="text-slate-200">
                    <span className="font-medium">{food.name}</span>
                    <span className="ml-2 text-xs text-slate-400">
                      {macroSummary(food)}
                    </span>
                  </span>
                  {/* Which figures came from where. An entry the user typed and
                      one a third-party database supplied warrant different
                      trust, and only this badge says which is which. */}
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${
                      food.source === 'user'
                        ? 'bg-slate-700 text-slate-300'
                        : 'bg-sky-500/20 text-sky-300'
                    }`}
                  >
                    {food.source === 'user' ? 'yours' : 'Open Food Facts'}
                  </span>
                  <span className="ml-auto flex items-center gap-2 text-xs">
                    <button
                      onClick={() => startEdit(food)}
                      disabled={busy}
                      className="text-slate-400 hover:text-emerald-300 disabled:opacity-40"
                    >
                      Edit
                    </button>
                    {confirmDelete === food.id ? (
                      <>
                        <button
                          onClick={() => remove(food.id)}
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
                        onClick={() => setConfirmDelete(food.id)}
                        disabled={busy}
                        aria-label={`Delete ${food.name}`}
                        // slate-400, not the slate-500 the supplements list
                        // uses for this button. The audit measured slate-500 on
                        // this background at ~3.8:1, below AA, and the wider
                        // contrast pass is its own piece of work -- but there is
                        // no reason for new code to add to what it has to fix.
                        className="text-slate-400 hover:text-rose-400 disabled:opacity-40"
                      >
                        Delete
                      </button>
                    )}
                  </span>
                  {confirmDelete === food.id && (
                    <p className="w-full text-xs text-slate-400">
                      This only removes it from autocomplete. Meals you logged
                      with it keep their numbers.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing === 'new' ? (
        <div className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
          <FoodForm
            draft={draft}
            setDraft={setDraft}
            onSave={save}
            onCancel={cancelEdit}
            busy={busy}
          />
        </div>
      ) : (
        <button
          onClick={startAdd}
          disabled={busy}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
        >
          + Add a food
        </button>
      )}

      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
    </section>
  )
}

/** The add/edit form. One component for both, because they are the same fields
 *  and two copies would drift.
 *
 *  All four macros are always shown, even for someone who does not track carbs
 *  or fat. A goal for an untracked macro is meaningless and Settings hides it;
 *  a food's carb content is a property of the food, it is already stored, and
 *  it becomes visible the day they switch tracking on. Hiding a stored number
 *  in the one screen built for correcting stored numbers would be backwards. */
function FoodForm({
  draft,
  setDraft,
  onSave,
  onCancel,
  busy,
}: {
  draft: Draft
  setDraft: (next: Draft) => void
  onSave: () => void
  onCancel: () => void
  busy: boolean
}) {
  const field =
    'rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 focus:border-emerald-500 focus:outline-none'

  const numberField = (
    key: 'servingSize' | 'calories' | 'protein' | 'carbs' | 'fat',
    label: string,
  ) => (
    <label className="block text-xs">
      <span className="mb-1 block text-slate-400">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        value={draft[key]}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        aria-label={label}
        className={`${field} w-full`}
      />
    </label>
  )

  return (
    <div className="space-y-2">
      <input
        value={draft.name}
        onChange={(event) => setDraft({ ...draft, name: event.target.value })}
        maxLength={MAX_FOOD_NAME}
        placeholder="Name"
        aria-label="Food name"
        className={`${field} w-full`}
      />

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {numberField('servingSize', 'Serving (g)')}
        {numberField('calories', 'Calories')}
        {numberField('protein', 'Protein (g)')}
        {numberField('carbs', 'Carbs (g)')}
        {numberField('fat', 'Fat (g)')}
      </div>
      <p className="text-xs text-slate-400">
        Macros are per serving. Leave carbs or fat blank if you do not know them
        — blank means “not recorded”, which is not the same as zero.
      </p>

      <div className="flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={onCancel} className="text-sm text-slate-400 hover:text-slate-200">
          Cancel
        </button>
      </div>
    </div>
  )
}
