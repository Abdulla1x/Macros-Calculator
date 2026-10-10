import { useEffect, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import FoodAutocomplete from '../components/FoodAutocomplete'
import MealAnalyzer from '../components/MealAnalyzer'
import { useAnalysis } from '../analysis/AnalysisContext'
import { useLogPanel } from '../components/log/useLogPanel'
import { announceMealsChanged } from '../lib/mealEvents'
import { useToast } from '../ui/toast'
import { localIsoDate, parseIsoDate } from '../lib/dates'
import type { LibraryContext } from '../lib/libraryMatch'
import { findByName } from '../lib/libraryMatch'
import {
  emptyRow,
  MAX_TEMPLATE_ITEMS,
  mealTotals,
  rowFromAnalyzedItem,
  rowFromTotals,
  rowIsValid,
  rowsFromTemplate,
  rowTotals,
  type Row,
} from '../lib/mealRows'
import { saveMeal, saveTemplate } from '../lib/saveMeal'
import { SOURCE_NAME, sourceAfterEdit } from '../lib/foodSources'
import { useSettings } from '../settings/SettingsContext'
import type {
  Food,
  FoodCreate,
  Meal,
  MealAnalysisResponse,
  MealTemplate,
  SharedMeal,
} from '../types'
import { Button } from '@/ui/button'
import { FIELD } from '@/ui/field'
import { DeleteIcon, KeepIcon, LogIcon } from '@/ui/icons'
import DayChips from '../components/log/DayChips'
import { useLiveMessage } from '../hooks/useLiveMessage'

/** "Use your saved numbers", when a row's name is one of the user's foods.
 *
 * Offered, never applied. The model never claimed this row is that food -- only
 * that the names happen to agree -- and rewriting macros on that basis is the
 * app deciding for the user. Where the user *did* attach the food, the match is
 * applied outright in rowFromAnalyzedItem, because picking it was the claim.
 *
 * Resolved on every render from the current name, so renaming a row re-asks the
 * question and there is no stored answer that can go stale. Tapping it hands the
 * work to selectFood, which already sets serving size, macros and the library
 * flag -- and deliberately leaves `weight` alone, which is what keeps the AI's
 * portion estimate while replacing the numbers it was guessing at.
 *
 * Expect this to fire less often than it sounds like it should, and that is not
 * a bug to fix by loosening the match. Measured against the real provider: the
 * model returns "Grilled chicken breast" where the library holds "Chicken
 * breast, raw", because it describes what was eaten and the library stores an
 * ingredient. So this mostly catches hand-typed rows and single-word foods.
 * Matching on a substring instead would start offering "Brown rice" for a row
 * called "rice", and an offer the user taps is a wrong number just as surely as
 * an automatic swap is. Attaching the food is the reliable path, and it is the
 * one the estimate itself is built around.
 */
function SavedNumbersOffer({
  name,
  foods,
  onUse,
}: {
  name: string
  foods: Food[]
  onUse: (food: Food) => void
}) {
  const match = findByName(name, foods)
  if (!match) return null
  return (
    <button
      type="button"
      onClick={() => onUse(match)}
      className="flex min-h-11 w-full flex-wrap items-center justify-between gap-2 rounded-control border-[1.5px] border-fact px-3 py-2 text-left text-small hover:bg-fact/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
    >
      <span className="font-semibold text-fact">Use your saved numbers for “{match.name}”</span>
      <span className="text-ink-2 tabular-nums">
        {match.calories} kcal · {match.protein} g P / {match.serving_size} g
      </span>
    </button>
  )
}

/** The Log panel's "Enter it by hand" screen, which is also where a meal is
 *  edited, a saved meal or a recent one is adjusted, and a pasted code or an
 *  AI estimate is checked before saving. It was the whole Log page until the
 *  panel (overhaul 0a); the AI box and the code box moved to the panel's start
 *  screen, and what they produce arrives here through router state. */
export default function LogMeal() {
  const location = useLocation()
  const { close } = useLogPanel()
  const toast = useToast()
  // Set when the dashboard's edit button navigated here; absent on a normal log.
  const editMeal = (location.state as { editMeal?: Meal } | null)?.editMeal ?? null
  // Set when navigating from a dashboard day-view, so a new meal defaults to the
  // day being viewed rather than today.
  //
  // A search param rather than router state, unlike the four below it: those
  // carry objects a URL cannot hold, while this is one ISO date. State does not
  // survive a reload, and this app has already shipped a bug from state
  // outliving what it described -- a shared-meal notice that stood over the next
  // meal typed by hand. A date in the address has neither problem, and it means
  // a half-finished entry survives a refresh on the day it was meant for.
  const logDate = useSearchParams()[0].get('date')
  // Set when a Saved meals template was tapped on the dashboard.
  const template =
    (location.state as { template?: MealTemplate } | null)?.template ?? null
  // Set when a recently-logged meal was tapped on the dashboard's "Log it
  // again" card. Carries a whole Meal, so it arrives through router state like
  // `template` rather than through the query string like `date` -- but note the
  // two travel TOGETHER: the meal says what to log and `?date=` says when, and
  // the meal's own date is deliberately ignored. Copying Tuesday's dinner is
  // logging dinner today, not editing Tuesday.
  const copyMeal = (location.state as { copyMeal?: Meal } | null)?.copyMeal ?? null
  // Set when a meal code was pasted below. The decoded meal and the code that
  // produced it travel together: the meal fills the form, and the code is the
  // only stable identity it has -- see the context string in the effect below.
  const shared =
    (location.state as { sharedMeal?: SharedMeal } | null)?.sharedMeal ?? null
  const sharedCode =
    (location.state as { sharedCode?: string } | null)?.sharedCode ?? null
  // Set when the start screen's "Use these ingredients" brought the AI
  // estimate here. The estimate itself stays in AnalysisProvider.
  const fromEstimate =
    (location.state as { fromEstimate?: boolean } | null)?.fromEstimate ?? false

  const { settings } = useSettings()
  const [rows, setRows] = useState<Row[]>([emptyRow()])
  const [mealName, setMealName] = useState('')
  const [mealDate, setMealDate] = useState(localIsoDate())

  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  // Both outcomes live in one state here, so one call covers the save
  // confirmation and every validation refusal.
  useLiveMessage(message?.text)
  const [saving, setSaving] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [analysisId, setAnalysisId] = useState<number | null>(null)
  // The AI estimate lives in AnalysisProvider, not here, so it outlasts this
  // page; reset() clears it once its meal is saved.
  const { reset: resetAnalysis, analysis: estimate, attached, library } = useAnalysis()
  // Read by the effect below without being one of its triggers: the estimate is
  // copied into the form once, when this screen opens for it, and never again --
  // re-copying when the library finished loading would wipe the user's edits.
  const estimateRef = useRef({ estimate, attached, library })
  estimateRef.current = { estimate, attached, library }
  // Whether what is currently in the form came out of a meal code, which is not
  // the same question as whether location.state holds one. The state survives a
  // save -- nothing clears a history entry -- so keying the notice off `shared`
  // directly left it standing over an empty form, and then over the next meal
  // the user typed by hand.
  const [fromCode, setFromCode] = useState(false)
  // Which day the meal in the form was copied from, or null. Held separately
  // from `copyMeal` for exactly the reason `fromCode` above is held separately
  // from `shared`: router state survives a save -- nothing clears a history
  // entry -- so a notice keyed off the navigation state directly would stand
  // over the empty form afterwards, and then over the next meal typed by hand.
  // That is not hypothetical; it is the bug `fromCode` was introduced to fix.
  const [copiedFrom, setCopiedFrom] = useState<string | null>(null)
  // The library as the analyzer saw it, kept only to offer a swap on rows the
  // user did not attach. Empty until an estimate is applied, so a hand-typed
  // meal is unaffected.
  const [libraryFoods, setLibraryFoods] = useState<Food[]>([])
  const lastContext = useRef(
    `${editMeal?.id ?? ''}|${sharedCode ?? ''}|${template?.name ?? ''}|${copyMeal?.id ?? ''}|${logDate ?? ''}`,
  )

  // Covers both mount and in-place navigation (edit → "Log a meal" and back).
  //
  // Precedence is explicit: editing an existing meal beats applying a template
  // or copying a logged one, and all of them beat a blank form. In practice only
  // one is ever set — they come from different dashboard buttons — but a
  // silently empty form is the failure mode if that ever stops being true, and
  // it reads as "the tap did nothing".
  useEffect(() => {
    if (editMeal) setRows([rowFromTotals(editMeal)])
    // A pasted code outranks a template: they are never both set, but if that
    // ever changes, the paste is what the user just did and the template is
    // stale navigation state.
    else if (shared) setRows(rowsFromTemplate(shared))
    else if (template) setRows(rowsFromTemplate(template))
    // A copied meal is flat -- `meals` stores totals and no ingredient rows --
    // so it loads as the single pass-through row an edit does, and for the same
    // reason. Below `template` only for tidiness; the two come from different
    // cards and are never both set.
    else if (copyMeal) setRows([rowFromTotals(copyMeal)])
    else setRows([emptyRow()])
    setMealName(editMeal?.name ?? shared?.name ?? template?.name ?? copyMeal?.name ?? '')
    // ⚠️ `copyMeal.date` is NOT in this chain, and its absence is the feature:
    // the date comes from `?date=`, which the dashboard set to the day it was
    // showing. A copy is a meal eaten today (or on the day you are looking at),
    // not a second copy of the day it came from -- see the column comments on
    // `meals`, which exist because `date` and `created_at` answer different
    // questions. `created_at` needs nothing here: POST /api/meals stamps it.
    setMealDate(editMeal?.date ?? logDate ?? localIsoDate())
    setAnalysisId(null)
    setLibraryFoods([])
    setFromCode(Boolean(shared))
    setCopiedFrom(copyMeal?.date ?? null)
    setMessage(null)
    // Below the resets on purpose: the estimate brings its own analysisId and
    // library, which the lines above would otherwise clear.
    const pending = estimateRef.current
    if (fromEstimate && pending.estimate && !editMeal && !shared && !template && !copyMeal) {
      applyAnalysis(pending.estimate, { attached: pending.attached, library: pending.library })
    }
    // Switching what this page is for -- a new meal, an edit, a template --
    // must take the analyzer with it. Without this, opening a meal to edit
    // leaves the previous meal's photos and estimate sitting above the form.
    //
    // Compared against the last context rather than guarded by a "first run"
    // ref: this effect also fires on mount, where there is nothing to switch
    // away from, and StrictMode double-invokes effects in development, which a
    // one-shot ref gets wrong on the second pass. Comparing identity is right
    // in both cases and needs no special-casing of either.
    //
    // The draft note is deliberately *not* cleared here. It is text the user
    // typed, and carrying it into an edit is a much smaller harm than deleting
    // it because they tapped a different button. Only a completed save clears
    // it, because only then is it certainly spent.
    // Keyed on the code, not on the decoded meal: a shared meal has no id, and
    // two different codes can carry the same name (someone re-sending a
    // corrected version), so comparing shared.name would silently fail to
    // notice the switch and leave the previous analysis sitting above the form.
    const context = `${editMeal?.id ?? ''}|${sharedCode ?? ''}|${template?.name ?? ''}|${copyMeal?.id ?? ''}|${logDate ?? ''}`
    if (lastContext.current !== context) {
      lastContext.current = context
    }
    // applyAnalysis only calls state setters, so it cannot go stale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editMeal, shared, sharedCode, template, copyMeal, logDate, fromEstimate])

  // Every edit to a row passes through here, so this is the one place the
  // provenance rule lives: change a number and the figures are the user's own
  // (lib/foodSources.ts). A patch that sets `source` itself -- a pick -- says
  // where its numbers came from and is taken at its word.
  const updateRow = (key: number, patch: Partial<Row>) => {
    setRows((current) =>
      current.map((row) =>
        row.key !== key
          ? row
          : {
              ...row,
              ...patch,
              source: patch.source ?? sourceAfterEdit(row.source, Object.keys(patch)),
            },
      ),
    )
  }

  // A library pick is already saved, so the tick stays away. A table or Open
  // Food Facts pick is NOT saved by picking (decided 2026-10-06): the tick
  // appears for it, unticked, and saving it keeps the pick's source.
  const selectFood = (key: number, food: FoodCreate, fromLibrary: boolean) => {
    updateRow(key, {
      name: food.name,
      servingSize: String(food.serving_size),
      calories: String(food.calories),
      protein: String(food.protein),
      carbs: food.carbs == null ? '' : String(food.carbs),
      fat: food.fat == null ? '' : String(food.fat),
      fromLibrary,
      saveToLibrary: false,
      source: food.source,
    })
  }

  const applyAnalysis = (analysis: MealAnalysisResponse, foods: LibraryContext) => {
    setRows(analysis.items.map((item) => rowFromAnalyzedItem(item, foods.attached)))
    setLibraryFoods(foods.library)
    setMealName((current) => current.trim() || analysis.meal_name)
    setAnalysisId(analysis.analysis_id)
    setMessage(null)
  }

  const validRows = rows.filter(rowIsValid)
  const totals = mealTotals(rows)

  const save = async () => {
    if (!mealName.trim()) {
      setMessage({ kind: 'error', text: 'Please enter a meal name.' })
      return
    }
    if (!mealDate) {
      setMessage({ kind: 'error', text: 'Please pick a date.' })
      return
    }
    if (validRows.length === 0) {
      setMessage({
        kind: 'error',
        text: 'Add at least one ingredient with weight, serving size, calories and protein.',
      })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      const meal = await saveMeal({
        rows,
        name: mealName,
        date: mealDate,
        editId: editMeal?.id ?? null,
        analysisId,
      })
      // Whether the estimate in AnalysisProvider went into this meal.
      const usedEstimate = analysisId !== null
      setAnalysisId(null)

      // The estimate outlives this screen, so one that went into this meal is
      // cleared (photos, note, the estimate itself), or the next meal would
      // open with this one's photos still attached. An unrelated one -- an
      // estimate still running for lunch while a snack is typed by hand -- is
      // left alone. reset() also clears the note's draft.
      if (usedEstimate) resetAnalysis()
      // The page under the panel never remounted, so it is told to reload.
      announceMealsChanged({ date: meal.date })
      // DESIGN.md: saving closes the panel. The toast is the confirmation the
      // inline "Saved ✓" used to be, and it lands on the page the meal is on.
      toast.show({ text: editMeal ? `Updated "${meal.name}".` : `Saved "${meal.name}".` })
      close()
    } catch (error) {
      setMessage({
        kind: 'error',
        text: error instanceof Error ? error.message : 'Saving failed',
      })
    } finally {
      setSaving(false)
    }
  }

  // Fires on its own rather than riding along with the meal save, so a meal can
  // be templated without being logged — and so it also works while editing an
  // existing meal, where there is no create to ride on.
  const saveAsTemplate = async () => {
    const name = mealName.trim()
    if (!name) {
      setMessage({ kind: 'error', text: 'Name the meal before keeping it as a saved meal.' })
      return
    }
    if (validRows.length === 0) {
      setMessage({
        kind: 'error',
        text: 'Add at least one complete ingredient before keeping it as a saved meal.',
      })
      return
    }
    if (validRows.length > MAX_TEMPLATE_ITEMS) {
      setMessage({
        kind: 'error',
        text: `A saved meal can hold at most ${MAX_TEMPLATE_ITEMS} ingredients.`,
      })
      return
    }
    setSavingTemplate(true)
    setMessage(null)
    try {
      const saved = await saveTemplate(rows, name)
      setMessage({
        kind: 'success',
        // Saving over a food corrects it; saving over a template throws away an
        // ingredient list, and there is no undo — so say which one happened.
        text: saved.created
          ? `Kept "${name}" as a saved meal.`
          : `Replaced your saved meal "${name}".`,
      })
    } catch (error) {
      setMessage({
        kind: 'error',
        text: error instanceof Error ? error.message : 'Saving the meal failed.',
      })
    } finally {
      setSavingTemplate(false)
    }
  }


  // One number field, in the redesign's look (DESIGN.md Inputs).
  const numberField = (
    row: Row,
    key: 'weight' | 'servingSize' | 'calories' | 'protein' | 'carbs' | 'fat',
    label: string,
    min = 0,
  ) => (
    <label className="grid gap-1">
      <span className="text-small text-ink-2">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={min}
        value={row[key]}
        onChange={(e) => updateRow(row.key, { [key]: e.target.value })}
        className={`${FIELD} tabular-nums`}
      />
    </label>
  )

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      {/* Ink and words, never a coloured box (DESIGN.md): a rule on the left
          sets a notice apart from the form it is about. */}
      {fromCode && (
        <p className="border-l-2 border-ink pl-3 text-small">
          These numbers came from whoever sent you the code. The app has not checked them and
          cannot: they may have been weighed, estimated or guessed. Change anything that looks
          wrong before you save; this is your copy now.
        </p>
      )}

      {copiedFrom && (
        <p className="border-l-2 border-ink pl-3 text-small">
          Copied from your{' '}
          <b>
            {parseIsoDate(copiedFrom).toLocaleDateString(undefined, {
              weekday: 'long',
              month: 'short',
              day: 'numeric',
            })}
          </b>{' '}
          log. Saving adds a new meal on the day below; the one you copied stays where it is.
        </p>
      )}

      {/* Only when editing: a new meal starts from the AI box on the panel's
          first screen, but re-estimating a meal already logged happens here,
          where the form it fills is right below. */}
      {editMeal && <MealAnalyzer onApply={applyAnalysis} />}

      <ol className="grid border-t border-rule">
        {rows.map((row, index) => (
          <li key={row.key} className="grid gap-3 border-b border-rule py-4">
            <div className="flex min-h-11 items-center justify-between gap-3">
              <h3 className="flex flex-wrap items-center gap-2 text-field-label text-ink-2">
                {rows.length === 1 ? 'Ingredient' : `Ingredient ${index + 1}`}
                {row.fromLibrary ? (
                  <span className="rounded-tag border-[1.5px] border-fact px-1.5 text-[11px] font-bold tracking-[0.04em] text-fact normal-case">
                    Your food
                  </span>
                ) : (
                  row.source !== 'user' && (
                    <span className="rounded-tag border-[1.5px] border-ink-2 px-1.5 text-[11px] font-bold tracking-[0.04em] normal-case">
                      from {SOURCE_NAME[row.source]}
                    </span>
                  )
                )}
              </h3>
              {rows.length > 1 && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
                  aria-label={`Remove ${row.name.trim() || `ingredient ${index + 1}`}`}
                >
                  <DeleteIcon size={18} aria-hidden />
                </Button>
              )}
            </div>

            <FoodAutocomplete
              value={row.name}
              onChange={(name) => updateRow(row.key, { name, fromLibrary: false })}
              onSelect={(food, fromLibrary) => selectFood(row.key, food, fromLibrary)}
            />

            <div className="grid grid-cols-2 gap-3">
              {numberField(row, 'weight', 'Weight eaten (g)')}
              {numberField(row, 'servingSize', 'Serving size (g)', 1)}
              {numberField(row, 'calories', 'Calories per serving')}
              {numberField(row, 'protein', 'Protein per serving (g)')}
              {settings?.track_carbs && numberField(row, 'carbs', 'Carbs per serving (g)')}
              {settings?.track_fat && numberField(row, 'fat', 'Fat per serving (g)')}
            </div>

            {!row.fromLibrary && (
              <SavedNumbersOffer
                name={row.name}
                foods={libraryFoods}
                onUse={(food) => selectFood(row.key, food, true)}
              />
            )}

            {!row.fromLibrary && row.name.trim() !== '' && (
              <label className="flex min-h-11 cursor-pointer items-center gap-3 text-small">
                <input
                  type="checkbox"
                  checked={row.saveToLibrary}
                  onChange={(e) => updateRow(row.key, { saveToLibrary: e.target.checked })}
                  className="size-5 shrink-0 accent-[var(--action)]"
                />
                Save “{row.name.trim()}” to my food library for next time
              </label>
            )}

            {rowIsValid(row) && (
              <p className="text-small text-ink-2 tabular-nums">
                This ingredient: {Math.round(rowTotals(row).calories)} kcal ·{' '}
                {Math.round(rowTotals(row).protein * 10) / 10} g protein
              </p>
            )}
          </li>
        ))}
      </ol>

      <Button
        variant="ghost"
        onClick={() => setRows((current) => [...current, emptyRow()])}
        className="justify-self-start"
      >
        <LogIcon size={18} aria-hidden />
        Add another ingredient
      </Button>

      <label className="grid gap-1">
        <span className="text-small text-ink-2">Meal name</span>
        <input
          type="text"
          value={mealName}
          onChange={(e) => setMealName(e.target.value)}
          placeholder="e.g. Chicken & rice bowl"
          className={FIELD}
        />
      </label>

      <DayChips legend="Day" value={mealDate} onChange={setMealDate} />

      {message && (
        <p className="border-l-2 border-ink pl-3 text-small">{message.text}</p>
      )}

      {/* The panel's footer, as on the AI result: the totals and Save always
          in reach, however many ingredients sit above. */}
      <div className="sticky bottom-0 -mx-4 grid gap-2 border-t border-rule bg-ground px-4 py-3 desk:-mx-7 desk:px-7">
        <p className="text-small text-ink-2 tabular-nums">
          <b className="text-ink">{Math.round(totals.calories)} kcal</b> ·{' '}
          {Math.round(totals.protein * 10) / 10} g protein
          {settings?.track_carbs && totals.carbs !== null && ` · ${Math.round(totals.carbs * 10) / 10} g carbs`}
          {settings?.track_fat && totals.fat !== null && ` · ${Math.round(totals.fat * 10) / 10} g fat`}
          {' '}({validRows.length} of {rows.length} ingredient{rows.length === 1 ? '' : 's'} counted)
        </p>
        <div className="flex flex-wrap gap-2">
          {/* Disabled while in flight, and that is load-bearing rather than
              cosmetic: the save is a read-then-write upsert with no lock, so
              two taps in quick succession would both find nothing, both
              insert, and collide on the unique index. */}
          <Button
            variant="secondary"
            onClick={saveAsTemplate}
            disabled={savingTemplate || saving}
            title="Save these ingredients to re-log in one tap"
          >
            <KeepIcon size={18} aria-hidden />
            {savingTemplate ? 'Saving…' : 'Keep as a saved meal'}
          </Button>
          <Button onClick={save} disabled={saving || savingTemplate} className="flex-1">
            {saving ? 'Saving…' : editMeal ? 'Update meal' : 'Save meal'}
          </Button>
        </div>
      </div>
    </div>
  )
}
