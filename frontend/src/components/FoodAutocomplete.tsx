import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Food, FoodCreate, OFFProduct } from '../types'

interface Props {
  value: string
  onChange: (name: string) => void
  onSelect: (food: FoodCreate) => void
}

/**
 * Type-ahead food search: local food library first, with an
 * Open Food Facts lookup as fallback. Picking an OFF result caches it
 * locally so the next search is instant.
 */
export default function FoodAutocomplete({ value, onChange, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const [localResults, setLocalResults] = useState<Food[]>([])
  const [offResults, setOffResults] = useState<OFFProduct[] | null>(null)
  const [offLoading, setOffLoading] = useState(false)
  const [offError, setOffError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const skipNextSearch = useRef(false)

  useEffect(() => {
    if (skipNextSearch.current) {
      skipNextSearch.current = false
      return
    }
    if (value.trim().length < 2) {
      setLocalResults([])
      setOffResults(null)
      return
    }
    const timer = setTimeout(() => {
      api
        .searchFoods(value.trim())
        .then((results) => {
          setLocalResults(results)
          setOffResults(null)
          setOffError(null)
          setOpen(true)
        })
        .catch(() => setLocalResults([]))
    }, 250)
    return () => clearTimeout(timer)
  }, [value])

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const pick = (food: FoodCreate) => {
    skipNextSearch.current = true
    onSelect(food)
    setOpen(false)
    setOffResults(null)
  }

  const pickOffProduct = async (product: OFFProduct) => {
    const food: FoodCreate = {
      name: product.name,
      serving_size: product.serving_size,
      calories: product.calories,
      protein: product.protein,
      carbs: product.carbs,
      fat: product.fat,
      source: 'openfoodfacts',
    }
    pick(food)
    // Cache it so the next search finds it locally; best-effort.
    try {
      await api.saveFood(food)
    } catch {
      /* ignore cache failures */
    }
  }

  const searchOff = async () => {
    setOffLoading(true)
    setOffError(null)
    try {
      setOffResults(await api.lookupOpenFoodFacts(value.trim()))
    } catch (error) {
      setOffError(error instanceof Error ? error.message : 'Lookup failed')
    } finally {
      setOffLoading(false)
    }
  }

  const macroSummary = (food: FoodCreate | OFFProduct) =>
    `${food.calories} kcal · ${food.protein} g protein / ${food.serving_size} g`

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => value.trim().length >= 2 && setOpen(true)}
        placeholder="Type a food name…"
        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
      />
      {open && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-slate-700 bg-slate-800 shadow-xl">
          {localResults.length > 0 && (
            <ul className="max-h-56 overflow-y-auto">
              {localResults.map((food) => (
                <li key={food.id}>
                  <button
                    type="button"
                    onClick={() => pick(food)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-700"
                  >
                    <span>
                      <span className="font-medium">{food.name}</span>
                      <span className="ml-2 text-xs text-slate-400">{macroSummary(food)}</span>
                    </span>
                    <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                      {food.source === 'user' ? 'library' : 'OFF'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {offResults === null ? (
            <button
              type="button"
              onClick={searchOff}
              disabled={offLoading}
              className="w-full border-t border-slate-700 px-3 py-2 text-left text-sm text-emerald-300 hover:bg-slate-700 disabled:opacity-60"
            >
              {offLoading
                ? 'Searching Open Food Facts…'
                : localResults.length === 0
                  ? `No "${value.trim()}" in your library — search Open Food Facts`
                  : 'Not listed? Search Open Food Facts'}
            </button>
          ) : offResults.length === 0 ? (
            <p className="border-t border-slate-700 px-3 py-2 text-sm text-slate-400">
              No results on Open Food Facts. Enter the macros manually below.
            </p>
          ) : (
            <ul className="max-h-56 overflow-y-auto border-t border-slate-700">
              {offResults.map((product, index) => (
                <li key={`${product.name}-${index}`}>
                  <button
                    type="button"
                    onClick={() => pickOffProduct(product)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-700"
                  >
                    <span>
                      <span className="font-medium">{product.name}</span>
                      {product.brand && (
                        <span className="ml-2 text-xs text-slate-500">{product.brand}</span>
                      )}
                      <span className="ml-2 text-xs text-slate-400">{macroSummary(product)}</span>
                    </span>
                    <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] uppercase text-sky-300">
                      OFF
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {offError && (
            <p className="border-t border-slate-700 px-3 py-2 text-sm text-rose-400">{offError}</p>
          )}
        </div>
      )}
    </div>
  )
}
