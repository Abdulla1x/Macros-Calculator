import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import FoodAutocomplete from '../components/FoodAutocomplete'
import MealAnalyzer from '../components/MealAnalyzer'
import MealCodeInput from '../components/MealCodeInput'
import { addDays, localIsoDate } from '../lib/dates'
import { clearNoteDraft } from '../lib/draft'
import { num } from '../lib/parse'
import { useSettings } from '../settings/SettingsContext'
import type {
  FoodCreate,
  Meal,
  MealAnalysisResponse,
  MealTemplate,
  SharedMeal,
} from '../types'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'

interface Row {
  key: number
  name: string
  weight: string
  servingSize: string
  calories: string
  protein: string
  carbs: string
  fat: string
  fromLibrary: boolean
  saveToLibrary: boolean
}

let rowCounter = 0
const emptyRow = (): Row => ({
  key: ++rowCounter,
  name: '',
  weight: '',
  servingSize: '100',
  calories: '',
  protein: '',
  carbs: '',
  fat: '',
  fromLibrary: false,
  saveToLibrary: true,
})

const rowIsValid = (row: Row) => {
  const weight = num(row.weight)
  const serving = num(row.servingSize)
  const calories = num(row.calories)
  const protein = num(row.protein)
  const carbs = num(row.carbs)
  const fat = num(row.fat)
  return (
    weight !== null && weight > 0 &&
    serving !== null && serving > 0 &&
    calories !== null && calories >= 0 &&
    protein !== null && protein >= 0 &&
    (row.carbs.trim() === '' || (carbs !== null && carbs >= 0)) &&
    (row.fat.trim() === '' || (fat !== null && fat >= 0))
  )
}

// Mirrors MAX_TEMPLATE_ITEMS in backend/app/schemas.py. Duplicated here only so
// the user gets a sentence instead of a bare 422 — the server is the authority.
const MAX_TEMPLATE_ITEMS = 30

// Ingredients aren't persisted with a meal, so editing loads the stored totals
// as one pass-through row: weight == serving size, so factor = 1 and the
// macros come through unchanged (same trick applyAnalysis uses).
//
// Takes anything carrying a name and the four macros, which is a meal or a
// template that has no items of its own.
const rowFromTotals = (
  source: Pick<Meal, 'name' | 'calories' | 'protein' | 'carbs' | 'fat'>,
): Row => ({
  ...emptyRow(),
  name: source.name,
  weight: '100',
  servingSize: '100',
  calories: String(source.calories),
  protein: String(source.protein),
  carbs: source.carbs == null ? '' : String(source.carbs),
  fat: source.fat == null ? '' : String(source.fat),
  saveToLibrary: false,
})

// Just the fields rowsFromTemplate actually reads, rather than a whole
// MealTemplate -- the same narrowing rowFromTotals above already uses. It is
// what lets a meal arriving in a share code, which has no id and was never a
// row in this account, be applied by the identical function.
type Applicable = Pick<
  MealTemplate,
  'name' | 'calories' | 'protein' | 'carbs' | 'fat' | 'items'
>

// A template keeps its ingredient rows, so applying one restores each at the
// weight it was saved at — which is the entire reason templates store items
// rather than just totals: the rice stays adjustable on its own.
//
// A template saved while editing an existing meal has no items, only totals,
// and so does every code made from a logged meal. Returning zero rows there
// would open the form empty and then refuse to save, complaining about
// ingredients the user never entered.
const rowsFromTemplate = (template: Applicable): Row[] =>
  template.items.length === 0
    ? [rowFromTotals(template)]
    : template.items.map((item) => ({
        ...emptyRow(),
        name: item.name,
        weight: String(item.weight_grams),
        servingSize: String(item.serving_size),
        calories: String(item.calories),
        protein: String(item.protein),
        carbs: item.carbs == null ? '' : String(item.carbs),
        fat: item.fat == null ? '' : String(item.fat),
        saveToLibrary: false,
      }))

const rowTotals = (row: Row) => {
  const factor = Number(row.weight) / Number(row.servingSize)
  const scale = (value: string) => {
    const parsed = num(value)
    return parsed === null ? null : parsed * factor
  }
  return {
    calories: (num(row.calories) ?? 0) * factor,
    protein: (num(row.protein) ?? 0) * factor,
    carbs: scale(row.carbs),
    fat: scale(row.fat),
  }
}

export default function LogMeal() {
  const navigate = useNavigate()
  const location = useLocation()
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
  // Set when a Quick log template was tapped on the dashboard.
  const template =
    (location.state as { template?: MealTemplate } | null)?.template ?? null
  // Set when a meal code was pasted below. The decoded meal and the code that
  // produced it travel together: the meal fills the form, and the code is the
  // only stable identity it has -- see the context string in the effect below.
  const shared =
    (location.state as { sharedMeal?: SharedMeal } | null)?.sharedMeal ?? null
  const sharedCode =
    (location.state as { sharedCode?: string } | null)?.sharedCode ?? null

  const { settings } = useSettings()
  const [rows, setRows] = useState<Row[]>([emptyRow()])
  const [mealName, setMealName] = useState('')
  const [mealDate, setMealDate] = useState(localIsoDate())

  // '' is unreachable through the input (the change handler drops it), but the
  // fallback keeps addDays away from a malformed date if it ever becomes so.
  const shiftMealDate = (delta: number) =>
    setMealDate((current) => addDays(current || localIsoDate(), delta))
  const dateChips = [
    { label: 'Today', date: localIsoDate() },
    { label: 'Yesterday', date: addDays(localIsoDate(), -1) },
  ]
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [analysisId, setAnalysisId] = useState<number | null>(null)
  // Bumped to remount MealAnalyzer. Its state is deliberately its own -- the
  // parent has no business reaching into ten pieces of it -- so a key is both
  // the smallest and the most complete way to reset it.
  const [analyzerNonce, setAnalyzerNonce] = useState(0)
  // Whether what is currently in the form came out of a meal code, which is not
  // the same question as whether location.state holds one. The state survives a
  // save -- nothing clears a history entry -- so keying the notice off `shared`
  // directly left it standing over an empty form, and then over the next meal
  // the user typed by hand.
  const [fromCode, setFromCode] = useState(false)
  const lastContext = useRef(
    `${editMeal?.id ?? ''}|${sharedCode ?? ''}|${template?.name ?? ''}|${logDate ?? ''}`,
  )

  // Covers both mount and in-place navigation (edit → "Log a meal" and back).
  //
  // Precedence is explicit: editing an existing meal beats applying a template,
  // and both beat a blank form. In practice only one is ever set — they come
  // from different dashboard buttons — but a silently empty form is the failure
  // mode if that ever stops being true, and it reads as "the tap did nothing".
  useEffect(() => {
    if (editMeal) setRows([rowFromTotals(editMeal)])
    // A pasted code outranks a template: they are never both set, but if that
    // ever changes, the paste is what the user just did and the template is
    // stale navigation state.
    else if (shared) setRows(rowsFromTemplate(shared))
    else if (template) setRows(rowsFromTemplate(template))
    else setRows([emptyRow()])
    setMealName(editMeal?.name ?? shared?.name ?? template?.name ?? '')
    setMealDate(editMeal?.date ?? logDate ?? localIsoDate())
    setAnalysisId(null)
    setFromCode(Boolean(shared))
    setMessage(null)
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
    const context = `${editMeal?.id ?? ''}|${sharedCode ?? ''}|${template?.name ?? ''}|${logDate ?? ''}`
    if (lastContext.current !== context) {
      lastContext.current = context
      setAnalyzerNonce((n) => n + 1)
    }
  }, [editMeal, shared, sharedCode, template, logDate])

  const updateRow = (key: number, patch: Partial<Row>) => {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const selectFood = (key: number, food: FoodCreate) => {
    updateRow(key, {
      name: food.name,
      servingSize: String(food.serving_size),
      calories: String(food.calories),
      protein: String(food.protein),
      carbs: food.carbs == null ? '' : String(food.carbs),
      fat: food.fat == null ? '' : String(food.fat),
      fromLibrary: true,
      saveToLibrary: false,
    })
  }

  const applyAnalysis = (analysis: MealAnalysisResponse) => {
    // AI macros are for the estimated portion, so weight == serving size and
    // the existing scaling logic passes them through unchanged (factor = 1).
    setRows(
      analysis.items.map((item) => ({
        ...emptyRow(),
        name: item.name,
        weight: String(item.portion_grams),
        servingSize: String(item.portion_grams),
        calories: String(item.calories),
        protein: String(item.protein),
        carbs: item.carbs == null ? '' : String(item.carbs),
        fat: item.fat == null ? '' : String(item.fat),
        saveToLibrary: false,
      })),
    )
    setMealName((current) => current.trim() || analysis.meal_name)
    setAnalysisId(analysis.analysis_id)
    setMessage(null)
  }

  const validRows = rows.filter(rowIsValid)
  const totals = validRows.reduce(
    (acc, row) => {
      const t = rowTotals(row)
      return {
        calories: acc.calories + t.calories,
        protein: acc.protein + t.protein,
        carbs: t.carbs === null ? acc.carbs : (acc.carbs ?? 0) + t.carbs,
        fat: t.fat === null ? acc.fat : (acc.fat ?? 0) + t.fat,
      }
    },
    { calories: 0, protein: 0, carbs: null as number | null, fat: null as number | null },
  )

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
      const payload = {
        date: mealDate,
        name: mealName.trim(),
        calories: Math.round(totals.calories * 100) / 100,
        protein: Math.round(totals.protein * 100) / 100,
        carbs: totals.carbs === null ? null : Math.round(totals.carbs * 100) / 100,
        fat: totals.fat === null ? null : Math.round(totals.fat * 100) / 100,
      }
      const meal = editMeal
        ? await api.updateMeal(editMeal.id, payload)
        : await api.createMeal(payload)

      // Best-effort: remember which AI analysis this meal came from.
      if (analysisId !== null) {
        await api.linkAnalysis(analysisId, meal.id).catch(() => null)
        setAnalysisId(null)
      }

      // Offer-to-cache: persist manually entered ingredients the user opted
      // in on. Best-effort — the meal is already saved, and a failed library
      // write must not surface as "Saving failed" (which would invite a
      // duplicate re-save).
      await Promise.all(
        validRows
          .filter((row) => !row.fromLibrary && row.saveToLibrary && row.name.trim())
          .map((row) =>
            api
              .saveFood({
                name: row.name.trim(),
                serving_size: Number(row.servingSize),
                calories: Number(row.calories),
                protein: Number(row.protein),
                carbs: num(row.carbs),
                fat: num(row.fat),
                source: 'user',
              })
              .catch(() => null),
          ),
      )

      if (editMeal) {
        navigate('/', { replace: true })
        return
      }
      setMessage({ kind: 'success', text: `Saved "${mealName.trim()}" ✓` })
      setRows([emptyRow()])
      setMealName('')
      // Remount the analyzer, which is the only way to clear all of its state
      // at once -- photos, previews, note, the estimate and the "Use these
      // ingredients" button. Leaving it standing meant the next meal opened
      // with the last one's photos still attached, and tapping apply again
      // pushed the previous meal's ingredients into a blank form.
      //
      // A remount rather than a pile of setters because MealAnalyzer's cleanup
      // effect revokes its object URLs; clearing the state by hand and
      // forgetting that leaks every preview blob for the life of the tab.
      //
      // The draft is cleared here too, and must be: the note is restored on
      // mount, so a remount that left it behind would hand the next meal the
      // description of the one just saved.
      clearNoteDraft()
      // The numbers it described are no longer on screen.
      setFromCode(false)
      setAnalyzerNonce((n) => n + 1)
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
      setMessage({ kind: 'error', text: 'Name the meal before saving it as a template.' })
      return
    }
    if (validRows.length === 0) {
      setMessage({
        kind: 'error',
        text: 'Add at least one complete ingredient before saving a template.',
      })
      return
    }
    if (validRows.length > MAX_TEMPLATE_ITEMS) {
      setMessage({
        kind: 'error',
        text: `A template can hold at most ${MAX_TEMPLATE_ITEMS} ingredients.`,
      })
      return
    }
    setSavingTemplate(true)
    setMessage(null)
    try {
      const saved = await api.saveMealTemplate({
        name,
        calories: Math.round(totals.calories * 100) / 100,
        protein: Math.round(totals.protein * 100) / 100,
        carbs: totals.carbs === null ? null : Math.round(totals.carbs * 100) / 100,
        fat: totals.fat === null ? null : Math.round(totals.fat * 100) / 100,
        items: validRows.map((row) => ({
          // A row is valid without a name, but the API requires one on every
          // item — so an unnamed ingredient gets a placeholder rather than a
          // 422 the user has no way to interpret.
          name: row.name.trim() || 'Ingredient',
          weight_grams: Number(row.weight),
          serving_size: Number(row.servingSize),
          calories: Number(row.calories),
          protein: Number(row.protein),
          carbs: num(row.carbs),
          fat: num(row.fat),
        })),
      })
      setMessage({
        kind: 'success',
        // Saving over a food corrects it; saving over a template throws away an
        // ingredient list, and there is no undo — so say which one happened.
        text: saved.created
          ? `Saved "${name}" as a template ☆`
          : `Replaced your existing "${name}" template ☆`,
      })
    } catch (error) {
      setMessage({
        kind: 'error',
        text: error instanceof Error ? error.message : 'Saving the template failed',
      })
    } finally {
      setSavingTemplate(false)
    }
  }


  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">{editMeal ? 'Edit meal' : 'Log a meal'}</h1>
        <p className="text-sm text-slate-400">
          {editMeal
            ? 'Adjust the details below — saving updates the existing entry.'
            : 'Start typing an ingredient — your food library and Open Food Facts fill in the macros.'}
        </p>
      </header>

      <MealCodeInput
        onLoaded={(sharedMeal, code) =>
          // Navigate rather than setRows: the effect above is the single place
          // that decides what this form holds, and it also resets the analyzer
          // and clears analysisId. That last one matters -- applyAnalysis sets
          // analysisId, and saving with a stale one would link an AI estimate
          // to a meal it never produced, quietly corrupting the calibration
          // figures on the Analytics page.
          navigate(`/log?date=${mealDate}`, {
            state: { sharedMeal, sharedCode: code },
            replace: true,
          })
        }
      />

      {fromCode && (
        <Card as="p" tone="warn" pad="sm" className="text-sm">
          These numbers came from whoever sent you the code. The app has not checked
          them and cannot — they may have been weighed, estimated or guessed. Change
          anything that looks wrong before you save; this is your copy now.
        </Card>
      )}

      <MealAnalyzer key={analyzerNonce} settings={settings} onApply={applyAnalysis} />

      <section className="space-y-4">
        {rows.map((row, index) => (
          <Card pad="sm" key={row.key}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-300">
                {rows.length === 1 ? 'Ingredient' : `Ingredient ${index + 1}`}
                {row.fromLibrary && (
                  <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] uppercase text-emerald-300">
                    from library
                  </span>
                )}
              </h2>
              {rows.length > 1 && (
                <button
                  onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
                  className="text-xs text-ink-faint hover:text-rose-400"
                >
                  Remove
                </button>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <FoodAutocomplete
                  value={row.name}
                  onChange={(name) => updateRow(row.key, { name, fromLibrary: false })}
                  onSelect={(food) => selectFood(row.key, food)}
                />
              </div>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Weight eaten (g)</span>
                <TextInput className="w-full"
                  type="number"
                  min={0}
                  value={row.weight}
                  onChange={(e) => updateRow(row.key, { weight: e.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Serving size (g)</span>
                <TextInput className="w-full"
                  type="number"
                  min={1}
                  value={row.servingSize}
                  onChange={(e) => updateRow(row.key, { servingSize: e.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Calories / serving</span>
                <TextInput className="w-full"
                  type="number"
                  min={0}
                  value={row.calories}
                  onChange={(e) => updateRow(row.key, { calories: e.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Protein / serving (g)</span>
                <TextInput className="w-full"
                  type="number"
                  min={0}
                  value={row.protein}
                  onChange={(e) => updateRow(row.key, { protein: e.target.value })}
                />
              </label>
              {settings?.track_carbs && (
                <label className="block text-sm">
                  <span className="mb-1 block text-xs text-slate-400">Carbs / serving (g)</span>
                  <TextInput className="w-full"
                    type="number"
                    min={0}
                    value={row.carbs}
                    onChange={(e) => updateRow(row.key, { carbs: e.target.value })}
                  />
                </label>
              )}
              {settings?.track_fat && (
                <label className="block text-sm">
                  <span className="mb-1 block text-xs text-slate-400">Fat / serving (g)</span>
                  <TextInput className="w-full"
                    type="number"
                    min={0}
                    value={row.fat}
                    onChange={(e) => updateRow(row.key, { fat: e.target.value })}
                  />
                </label>
              )}
            </div>

            {!row.fromLibrary && row.name.trim() !== '' && (
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={row.saveToLibrary}
                  onChange={(e) => updateRow(row.key, { saveToLibrary: e.target.checked })}
                  className="h-3.5 w-3.5 accent-emerald-500"
                />
                Save “{row.name.trim()}” to my food library for next time
              </label>
            )}

            {rowIsValid(row) && (
              <p className="mt-3 text-xs text-slate-400">
                This ingredient: {Math.round(rowTotals(row).calories)} kcal ·{' '}
                {Math.round(rowTotals(row).protein * 10) / 10} g protein
              </p>
            )}
          </Card>
        ))}

        <button
          onClick={() => setRows((current) => [...current, emptyRow()])}
          className="w-full rounded-xl border border-dashed border-slate-700 py-3 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
        >
          + Add another ingredient
        </button>
      </section>

      <Card as="section">
        <h2 className="mb-3 font-semibold">Meal details</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-slate-400">Meal name</span>
            <TextInput className="w-full"
              type="text"
              value={mealName}
              onChange={(e) => setMealName(e.target.value)}
              placeholder="e.g. Chicken & rice bowl"
            />
          </label>
          {/* Nearly every meal is logged today or yesterday, so a chip is fewer
              taps than any picker, and the steppers cover the rest of the week.
              Mirrors the Dashboard header's controls rather than inventing a
              second idiom for the same job.

              The label cannot wrap the control here -- the steppers sit beside
              the input, and interactive content inside a <label> has murky
              click-forwarding behaviour. htmlFor/id instead, which is the first
              explicit association in this codebase; everything else wraps. */}
          <div>
            <label htmlFor="meal-date" className="mb-1 block text-xs text-slate-400">
              Date
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => shiftMealDate(-1)}
                aria-label="Previous day"
                className="shrink-0 rounded-control border border-line bg-surface px-2.5 py-2 text-slate-300 hover:bg-raised"
              >
                ◀
              </button>
              <TextInput className="w-full flex-1"
                id="meal-date"
                type="date"
                value={mealDate}
                max={localIsoDate()}
                // Ignore a cleared field rather than storing ''. addDays throws on
                // a malformed date by design, so an empty value would turn the
                // very next stepper tap into an exception. Dashboard's picker
                // already guards the same way.
                onChange={(e) => e.target.value && setMealDate(e.target.value)}
              />
              <button
                type="button"
                onClick={() => shiftMealDate(1)}
                disabled={mealDate >= localIsoDate()}
                aria-label="Next day"
                className="shrink-0 rounded-control border border-line bg-surface px-2.5 py-2 text-slate-300 hover:bg-raised disabled:cursor-not-allowed disabled:opacity-40"
              >
                ▶
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {dateChips.map((chip) => (
                <button
                  key={chip.label}
                  type="button"
                  onClick={() => setMealDate(chip.date)}
                  aria-pressed={mealDate === chip.date}
                  className={`rounded-full px-2.5 py-0.5 text-xs ${
                    mealDate === chip.date
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : 'bg-raised text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-800/60 px-4 py-3">
          <p className="text-sm">
            <span className="font-semibold text-amber-400">{Math.round(totals.calories)} kcal</span>
            <span className="mx-2 text-ink-faint">·</span>
            <span className="font-semibold text-emerald-400">
              {Math.round(totals.protein * 10) / 10} g protein
            </span>
            {settings?.track_carbs && totals.carbs !== null && (
              <>
                <span className="mx-2 text-ink-faint">·</span>
                <span className="font-semibold text-sky-400">
                  {Math.round(totals.carbs * 10) / 10} g carbs
                </span>
              </>
            )}
            {settings?.track_fat && totals.fat !== null && (
              <>
                <span className="mx-2 text-ink-faint">·</span>
                <span className="font-semibold text-rose-400">
                  {Math.round(totals.fat * 10) / 10} g fat
                </span>
              </>
            )}
            <span className="ml-2 text-xs text-ink-faint">
              ({validRows.length} of {rows.length} ingredient{rows.length === 1 ? '' : 's'} counted)
            </span>
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {/* Disabled while in flight, and that is load-bearing rather than
                cosmetic: the save is a read-then-write upsert with no lock, so
                two taps in quick succession would both find nothing, both
                insert, and collide on the unique index. */}
            <button
              onClick={saveAsTemplate}
              disabled={savingTemplate || saving}
              title="Save these ingredients to re-log in one tap"
              className="rounded-lg border border-slate-700 px-5 py-2.5 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
            >
              {savingTemplate ? 'Saving…' : '☆ Save as template'}
            </button>
            <button
              onClick={save}
              disabled={saving || savingTemplate}
              className="rounded-lg bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {saving ? 'Saving…' : editMeal ? 'Update meal' : 'Save meal'}
            </button>
          </div>
        </div>

        {message && (
          <p
            className={`mt-3 text-sm ${message.kind === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}
          >
            {message.text}
          </p>
        )}
      </Card>
    </div>
  )
}
