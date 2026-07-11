import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import FoodAutocomplete from '../components/FoodAutocomplete'
import MealAnalyzer from '../components/MealAnalyzer'
import { localIsoDate } from '../lib/dates'
import type { FoodCreate, Meal, MealAnalysisResponse, Settings } from '../types'

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

// Non-numeric input ("abc", "1e999") becomes null, not NaN — NaN would pass
// validation and then serialize as null in the payload, silently corrupting
// the meal.
const num = (value: string) => {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

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

// Ingredients aren't persisted with a meal, so editing loads the stored totals
// as one pass-through row: weight == serving size, so factor = 1 and the
// macros come through unchanged (same trick applyAnalysis uses).
const rowFromMeal = (meal: Meal): Row => ({
  ...emptyRow(),
  name: meal.name,
  weight: '100',
  servingSize: '100',
  calories: String(meal.calories),
  protein: String(meal.protein),
  carbs: meal.carbs == null ? '' : String(meal.carbs),
  fat: meal.fat == null ? '' : String(meal.fat),
  saveToLibrary: false,
})

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

  const [settings, setSettings] = useState<Settings | null>(null)
  const [rows, setRows] = useState<Row[]>([emptyRow()])
  const [mealName, setMealName] = useState('')
  const [mealDate, setMealDate] = useState(localIsoDate())
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [analysisId, setAnalysisId] = useState<number | null>(null)

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => null)
  }, [])

  // Covers both mount and in-place navigation (edit → "Log a meal" and back).
  useEffect(() => {
    setRows(editMeal ? [rowFromMeal(editMeal)] : [emptyRow()])
    setMealName(editMeal?.name ?? '')
    setMealDate(editMeal?.date ?? localIsoDate())
    setAnalysisId(null)
    setMessage(null)
  }, [editMeal])

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
    } catch (error) {
      setMessage({
        kind: 'error',
        text: error instanceof Error ? error.message : 'Saving failed',
      })
    } finally {
      setSaving(false)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm placeholder-slate-500 focus:border-emerald-500 focus:outline-none'

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold">{editMeal ? 'Edit meal' : 'Log a meal'}</h2>
        <p className="text-sm text-slate-400">
          {editMeal
            ? 'Adjust the details below — saving updates the existing entry.'
            : 'Start typing an ingredient — your food library and Open Food Facts fill in the macros.'}
        </p>
      </header>

      <MealAnalyzer settings={settings} onApply={applyAnalysis} />

      <section className="space-y-4">
        {rows.map((row, index) => (
          <div key={row.key} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-300">
                {rows.length === 1 ? 'Ingredient' : `Ingredient ${index + 1}`}
                {row.fromLibrary && (
                  <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] uppercase text-emerald-300">
                    from library
                  </span>
                )}
              </h3>
              {rows.length > 1 && (
                <button
                  onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
                  className="text-xs text-slate-500 hover:text-rose-400"
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
                <input
                  type="number"
                  min={0}
                  value={row.weight}
                  onChange={(e) => updateRow(row.key, { weight: e.target.value })}
                  className={inputClass}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Serving size (g)</span>
                <input
                  type="number"
                  min={1}
                  value={row.servingSize}
                  onChange={(e) => updateRow(row.key, { servingSize: e.target.value })}
                  className={inputClass}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Calories / serving</span>
                <input
                  type="number"
                  min={0}
                  value={row.calories}
                  onChange={(e) => updateRow(row.key, { calories: e.target.value })}
                  className={inputClass}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-slate-400">Protein / serving (g)</span>
                <input
                  type="number"
                  min={0}
                  value={row.protein}
                  onChange={(e) => updateRow(row.key, { protein: e.target.value })}
                  className={inputClass}
                />
              </label>
              {settings?.track_carbs && (
                <label className="block text-sm">
                  <span className="mb-1 block text-xs text-slate-400">Carbs / serving (g)</span>
                  <input
                    type="number"
                    min={0}
                    value={row.carbs}
                    onChange={(e) => updateRow(row.key, { carbs: e.target.value })}
                    className={inputClass}
                  />
                </label>
              )}
              {settings?.track_fat && (
                <label className="block text-sm">
                  <span className="mb-1 block text-xs text-slate-400">Fat / serving (g)</span>
                  <input
                    type="number"
                    min={0}
                    value={row.fat}
                    onChange={(e) => updateRow(row.key, { fat: e.target.value })}
                    className={inputClass}
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
          </div>
        ))}

        <button
          onClick={() => setRows((current) => [...current, emptyRow()])}
          className="w-full rounded-xl border border-dashed border-slate-700 py-3 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
        >
          + Add another ingredient
        </button>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-3 font-semibold">Meal details</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-slate-400">Meal name</span>
            <input
              type="text"
              value={mealName}
              onChange={(e) => setMealName(e.target.value)}
              placeholder="e.g. Chicken & rice bowl"
              className={inputClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-slate-400">Date</span>
            <input
              type="date"
              value={mealDate}
              onChange={(e) => setMealDate(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-800/60 px-4 py-3">
          <p className="text-sm">
            <span className="font-semibold text-amber-400">{Math.round(totals.calories)} kcal</span>
            <span className="mx-2 text-slate-600">·</span>
            <span className="font-semibold text-emerald-400">
              {Math.round(totals.protein * 10) / 10} g protein
            </span>
            {settings?.track_carbs && totals.carbs !== null && (
              <>
                <span className="mx-2 text-slate-600">·</span>
                <span className="font-semibold text-sky-400">
                  {Math.round(totals.carbs * 10) / 10} g carbs
                </span>
              </>
            )}
            {settings?.track_fat && totals.fat !== null && (
              <>
                <span className="mx-2 text-slate-600">·</span>
                <span className="font-semibold text-rose-400">
                  {Math.round(totals.fat * 10) / 10} g fat
                </span>
              </>
            )}
            <span className="ml-2 text-xs text-slate-500">
              ({validRows.length} of {rows.length} ingredient{rows.length === 1 ? '' : 's'} counted)
            </span>
          </p>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {saving ? 'Saving…' : editMeal ? 'Update meal' : 'Save meal'}
          </button>
        </div>

        {message && (
          <p
            className={`mt-3 text-sm ${message.kind === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}
          >
            {message.text}
          </p>
        )}
      </section>
    </div>
  )
}
