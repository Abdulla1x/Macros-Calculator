import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { MAX_FOOD_NAME, validateFood } from '../../lib/limits'
import { num } from '../../lib/parse'
import type { Food, FoodCreate } from '../../types'
import Card from '../ui/Card'
import TextInput from '../ui/TextInput'
import Field from '../ui/Field'
import Button from '../ui/Button'
import ShowAllToggle, { COLLAPSED_ROWS } from './ShowAllToggle'

/** The saved-food library: see it, correct it, rename it, delete it.
 *
 * One of the sections of the Settings page. They live in this folder rather
 * than in Settings.tsx itself, which otherwise carries every one of them at
 * once. This is the largest -- a list that grows on its own, a filter, an
 * inline form and a delete confirmation.
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
  const [expanded, setExpanded] = useState(false)

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

  // Capped *after* filtering, not before: a filter that already narrows 62 foods
  // to three has answered the question the expander asks, and offering to expand
  // three rows would be noise.
  //
  // The row being edited is kept on screen whatever it sorts to. Expand the
  // list, correct a food near the bottom, then collapse, and without this its
  // half-typed form is unmounted while `editing` still points at it -- the edit
  // is not lost, it is just somewhere the user cannot see, which is worse than
  // either losing it or keeping it.
  const visible = useMemo(() => {
    if (expanded) return shown
    const head = shown.slice(0, COLLAPSED_ROWS)
    if (typeof editing !== 'number' || head.some((food) => food.id === editing)) {
      return head
    }
    const edited = shown.find((food) => food.id === editing)
    return edited ? [...head, edited] : head
  }, [shown, expanded, editing])

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
      if (editing === 'new') {
        await api.saveFood(body)
        // load() re-sorts by name, so a food added while collapsed can land past
        // COLLAPSED_ROWS and read as "nothing happened". Expanding is the only
        // answer that is true whatever the new name sorts to.
        setExpanded(true)
      } else if (typeof editing === 'number') {
        await api.updateFood(editing, body)
      }
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
    <Card as="section">
      <h2 className="mb-1 font-semibold">🥫 Food library</h2>
      <p className="mb-4 text-sm text-slate-400">
        The foods autocomplete offers you when you log a meal. Things land here
        on their own:{' '}
        <strong className="text-slate-300">
          every Open Food Facts result you pick is saved here automatically
        </strong>
        , along with anything you ticked “save to library” on and any ingredient
        you saved from an AI estimate. You can also add one yourself with the
        button below. This is where you correct one that is wrong. Changes here
        save straight away — nothing on this tab waits for a Save.
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
          <TextInput
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by name…"
            aria-label="Filter food library"
            className="min-w-0 flex-1"
          />
          <span className="text-xs text-slate-400">
            {items.length} food{items.length === 1 ? '' : 's'}
            {filter.trim() !== '' && ` · ${shown.length} matching`}
          </span>
        </div>
      )}

      {/* Above the list, not below it. On a library of any size a control
          rendered after every row is a control nobody finds. */}
      {editing === 'new' ? (
        <div className="mb-3 rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
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
          className="mb-3 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
        >
          + Add a food
        </button>
      )}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400">
          Nothing saved yet. Use <strong className="text-slate-300">+ Add a food</strong>{' '}
          above to enter one yourself. Foods also arrive here on their own: pick
          one from Open Food Facts while logging a meal, save an ingredient from
          an AI estimate, or tick “save to library” on one you typed.
        </p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing matches “{filter.trim()}”.</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {visible.map((food) => (
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

      <ShowAllToggle
        total={shown.length}
        cap={COLLAPSED_ROWS}
        expanded={expanded}
        onToggle={() => {
          setExpanded((current) => !current)
          // An armed "Delete for good" must not survive out of sight. A row
          // scrolled away still holding its confirmation would come back armed
          // on the next expand, one tap from deleting something the user had
          // already moved on from.
          setConfirmDelete(null)
        }}
        noun="food"
      />

      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
    </Card>
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
    'rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-base sm:text-sm text-slate-200 focus:border-emerald-500'

  const numberField = (
    key: 'servingSize' | 'calories' | 'protein' | 'carbs' | 'fat',
    label: string,
  ) => (
    <Field size="xs" label={<>{label}</>}>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        value={draft[key]}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        aria-label={label}
        className={`${field} w-full`}
      />
    </Field>
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
        <Button
          onClick={onSave}
          disabled={busy}
          className="px-3 py-1.5"
        >
          {busy ? 'Saving…' : 'Save'}
        </Button>
        <button onClick={onCancel} className="text-sm text-slate-400 hover:text-slate-200">
          Cancel
        </button>
      </div>
    </div>
  )
}
