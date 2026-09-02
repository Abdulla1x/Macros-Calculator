import { useState } from 'react'
import { api } from '../api/client'
import { MAX_FOOD_NAME, validateFood } from '../lib/limits'
import { findByName, foodFromAnalyzedItem } from '../lib/libraryMatch'
import { num } from '../lib/parse'
import type { AnalyzedItem, Food } from '../types'
import Button from './ui/Button'
import Field from './ui/Field'
import TextInput from './ui/TextInput'

/** "Save this ingredient to my library", on one item of an AI estimate.
 *
 * The gap this closes: an estimate could only reach the library by way of a
 * logged meal. Applying it, then ticking the per-row box, then saving the meal
 * wrote the food -- so describing a dip you eat every week meant either logging
 * a meal you did not eat or paying for the same estimate again next time.
 * Saving from here writes the food and nothing else.
 *
 * The numbers are shown before they are stored, and that is the point rather
 * than a courtesy. A meal is a record of one day; a library food is a claim
 * about a food that will fill in every future meal that names it. Two fields
 * are worth a human eye:
 *
 *  * The NAME. The model describes what was eaten -- "Grilled chicken breast" --
 *    where a library stores an ingredient, "Chicken breast, raw". That gap is
 *    measured, not theoretical, and is the whole reason matched_food_name exists
 *    (see lib/libraryMatch.ts).
 *  * WHETHER IT REPLACES SOMETHING. POST /api/foods is an upsert on the lowered
 *    name, so saving over a food whose numbers you weighed yourself overwrites
 *    them with an estimate, silently and with no undo.
 *
 * Macros are stored per 100 g, converted by foodFromAnalyzedItem. Serving size
 * is fixed here rather than editable: changing it would have to rescale four
 * numbers underneath the user mid-edit, and the library editor in Settings is
 * where a food gets a different serving.
 */

interface Draft {
  name: string
  calories: string
  protein: string
  carbs: string
  fat: string
}

const SERVING_SIZE = 100

const draftFor = (item: AnalyzedItem): Draft => {
  const food = foodFromAnalyzedItem(item, SERVING_SIZE)
  return {
    name: food.name,
    calories: String(food.calories),
    protein: String(food.protein),
    carbs: food.carbs === null ? '' : String(food.carbs),
    fat: food.fat === null ? '' : String(food.fat),
  }
}

export default function SaveIngredientToLibrary({
  item,
  library,
  savedAs,
  onSaved,
}: {
  item: AnalyzedItem
  /** The library as it was when the panel opened. Used only to warn about a
   *  replacement -- deliberately not written back to, so nothing this component
   *  saves can turn into a "use your saved numbers" offer for the very row it
   *  came from. */
  library: Food[]
  /** The name it was saved under, or null if it has not been. A name rather
   *  than a flag because renaming before saving is the common case, and a bare
   *  "saved ✓" would send the user looking in the library for a name that is
   *  not there. */
  savedAs: string | null
  onSaved: (name: string) => void
}) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // portion_grams is the divisor in the conversion, and AnalyzedItem carries no
  // numeric bounds -- the provider rejects them in a structured-output schema --
  // so zero and negatives really do arrive. Offering a control that cannot
  // produce a sane number is worse than not offering it.
  if (!(item.portion_grams > 0)) return null

  if (savedAs !== null) {
    return (
      <p className="mt-1.5 text-xs text-brand">
        {savedAs === item.name
          ? 'Saved to your food library ✓'
          : `Saved to your food library as “${savedAs}” ✓`}
      </p>
    )
  }

  if (draft === null) {
    return (
      <button
        onClick={() => {
          setError('')
          setDraft(draftFor(item))
        }}
        aria-expanded={false}
        className="mt-1.5 text-xs text-ink-muted underline decoration-dotted hover:text-brand"
      >
        Save “{item.name}” to my food library
      </button>
    )
  }

  // Recomputed from the current name on every render, so correcting the name out
  // of a collision clears the warning with no stored answer to go stale -- the
  // same reason LogMeal resolves its own saved-numbers offer per render.
  const replaces = findByName(draft.name, library)

  const save = async () => {
    const calories = num(draft.calories)
    const protein = num(draft.protein)
    const carbs = num(draft.carbs)
    const fat = num(draft.fat)

    const problem = validateFood(draft.name, SERVING_SIZE, calories, protein, carbs, fat)
    if (problem) {
      setError(problem)
      return
    }

    setBusy(true)
    try {
      await api.saveFood({
        name: draft.name.trim(),
        serving_size: SERVING_SIZE,
        // Non-null by the validator above, which refuses null for all three.
        calories: calories as number,
        protein: protein as number,
        carbs,
        fat,
        source: 'user',
      })
      setDraft(null)
      setError('')
      onSaved(draft.name.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const macroField = (key: 'calories' | 'protein' | 'carbs' | 'fat', label: string) => (
    <Field size="xs" label={<>{label}</>}>
      <TextInput
        type="number"
        inputMode="decimal"
        min={0}
        pad="sm"
        value={draft[key]}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        aria-label={`${label} per 100 g`}
        className="w-full"
      />
    </Field>
  )

  return (
    <div className="mt-2 space-y-2 rounded-control border border-line-strong bg-app px-3 py-2">
      <Field size="xs" label={<>Name</>}>
        <TextInput
          value={draft.name}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          maxLength={MAX_FOOD_NAME}
          pad="sm"
          aria-label="Food name"
          className="w-full"
        />
      </Field>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {macroField('calories', 'Calories')}
        {macroField('protein', 'Protein (g)')}
        {macroField('carbs', 'Carbs (g)')}
        {macroField('fat', 'Fat (g)')}
      </div>

      <p className="text-xs text-ink-faint">
        Stored <strong className="text-ink-muted">per 100 g</strong>, scaled from
        the {Math.round(item.portion_grams)} g this estimate assumed — so it works
        at any weight next time. Blank carbs or fat means “not recorded”, which is
        not the same as zero.
      </p>

      {replaces && (
        <p className="rounded-control bg-amber-500/10 px-2 py-1.5 text-xs text-amber-300">
          You already have a food called “{replaces.name}”. Saving replaces its
          numbers with these, and there is no undo — rename this one to keep both.
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={busy} className="px-3 py-1.5 text-sm">
          {busy ? 'Saving…' : replaces ? 'Replace it' : 'Save to library'}
        </Button>
        <button
          onClick={() => {
            setDraft(null)
            setError('')
          }}
          className="text-sm text-ink-muted hover:text-ink"
        >
          Cancel
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  )
}
