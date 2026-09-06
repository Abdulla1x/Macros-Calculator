import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Food, FoodCreate, OFFProduct } from '../types'
import TextInput, { inputSurfaceClass } from './ui/TextInput'
import { useLiveMessage } from '../hooks/useLiveMessage'

interface Props {
  value: string
  onChange: (name: string) => void
  onSelect: (food: FoodCreate) => void
}

/** One row of the suggestion list, from either source.
 *
 * The two lists are FLATTENED into a single array rather than kept as two, and
 * that is what makes the keyboard work. ARIA's combobox pattern moves a single
 * cursor through one listbox; two lists would need either two cursors or a
 * group structure, and the rows already carry a "library"/"OFF" badge that says
 * where each came from -- so the grouping is visible without being structural. */
type Suggestion =
  | { kind: 'local'; food: Food }
  | { kind: 'off'; product: OFFProduct }

/**
 * Type-ahead food search: local food library first, with an
 * Open Food Facts lookup as fallback. Picking an OFF result caches it
 * locally so the next search is instant.
 *
 * ⚠ THIS WAS MOUSE-ONLY UNTIL NOW, on the meal-logging path. There was no
 * combobox role, no aria-expanded, no way to reach a suggestion from the
 * keyboard and no way to dismiss the panel except by clicking elsewhere -- so
 * the list could be seen but not used, and a screen reader was never told a
 * list had appeared at all. Phase 15 deferred this to "Phase 18's Modal";
 * Phase 18 shipped the Modal and never touched it.
 *
 * ⚠ THE ROWS ARE NO LONGER BUTTONS. An element with role="option" must not
 * contain a focusable child: the pattern keeps DOM focus in the input at all
 * times and moves a virtual cursor with aria-activedescendant, so a button
 * inside an option gives the user a second, conflicting way to focus a row and
 * breaks the cursor. Click still works -- a click handler needs no button --
 * and keyboard reach now comes from the combobox instead.
 *
 * The Open Food Facts button stays OUTSIDE the listbox and out of the arrow-key
 * ring, because it is not a suggestion: it starts a search. It remains a real
 * button and a normal tab stop, which is the honest description of it.
 */
export default function FoodAutocomplete({ value, onChange, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const [localResults, setLocalResults] = useState<Food[]>([])
  const [offResults, setOffResults] = useState<OFFProduct[] | null>(null)
  const [offLoading, setOffLoading] = useState(false)
  const [offError, setOffError] = useState<string | null>(null)
  useLiveMessage(offError)
  // -1 is "no row is current", which is the state the panel opens in. Typing a
  // name and pressing Enter must submit what was typed, not silently swap in
  // whatever happened to be first in a list the user has not looked at.
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const skipNextSearch = useRef(false)
  // Stable across renders and unique per instance -- LogMeal renders one of
  // these per ingredient row, so a hard-coded id would repeat down the page and
  // aria-activedescendant would resolve to the first one every time.
  const listId = useId()
  const optionId = (index: number) => `${listId}-option-${index}`

  const suggestions: Suggestion[] = [
    ...localResults.map((food): Suggestion => ({ kind: 'local', food })),
    ...(offResults ?? []).map((product): Suggestion => ({ kind: 'off', product })),
  ]

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
    // `stale` stops a slow response for a previous query from overwriting the
    // current results (the timer only guards the debounce, not the fetch).
    let stale = false
    const timer = setTimeout(() => {
      api
        .searchFoods(value.trim())
        .then((results) => {
          if (stale) return
          setLocalResults(results)
          setOffResults(null)
          setOffError(null)
          setOpen(true)
        })
        .catch(() => {
          if (!stale) setLocalResults([])
        })
    }, 250)
    return () => {
      stale = true
      clearTimeout(timer)
    }
  }, [value])

  // Any change to what is in the list invalidates where the cursor was. Without
  // this, typing another letter leaves the cursor on row 3 of a list that now
  // has two rows, and Enter picks whatever slid into that position.
  useEffect(() => {
    setActiveIndex(-1)
  }, [localResults, offResults])

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  // Keep the cursor visible. The list scrolls at max-h-56, so a cursor moved
  // past the fold is a cursor the user cannot see, which reads as the arrow key
  // having done nothing.
  useEffect(() => {
    if (activeIndex < 0) return
    listRef.current
      ?.querySelector(`#${CSS.escape(optionId(activeIndex))}`)
      ?.scrollIntoView({ block: 'nearest' })
  })

  const pick = (food: FoodCreate) => {
    skipNextSearch.current = true
    onSelect(food)
    setOpen(false)
    setOffResults(null)
    setActiveIndex(-1)
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

  /** Both sources go through here, so keyboard and mouse cannot diverge --
   *  and both inherit skipNextSearch, which is what stops the name written
   *  back into the input from re-opening the panel it just closed. */
  const choose = (suggestion: Suggestion) => {
    if (suggestion.kind === 'local') pick(suggestion.food)
    else void pickOffProduct(suggestion.product)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      // Only ever closes the panel. Focus is already in the input and stays
      // there, so there is nothing to restore.
      if (open) {
        event.preventDefault()
        setOpen(false)
        setActiveIndex(-1)
      }
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (suggestions.length === 0) return
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => {
        // From "no row", Down lands on the first and Up on the last. After that
        // it wraps, so a long list is reachable from either end.
        if (current < 0) return step === 1 ? 0 : suggestions.length - 1
        return (current + step + suggestions.length) % suggestions.length
      })
      return
    }
    if (event.key === 'Enter') {
      const suggestion = open && activeIndex >= 0 ? suggestions[activeIndex] : undefined
      if (!suggestion) return
      // Only when a row is genuinely current. Otherwise Enter belongs to the
      // form around this field.
      event.preventDefault()
      choose(suggestion)
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

  const listboxOpen = open && suggestions.length > 0

  return (
    <div ref={containerRef} className="relative">
      <TextInput
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => value.trim().length >= 2 && setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Type a food name…"
        className="w-full"
        role="combobox"
        aria-expanded={listboxOpen}
        aria-controls={listboxOpen ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={
          listboxOpen && activeIndex >= 0 ? optionId(activeIndex) : undefined
        }
      />
      {/* The panel below is deliberately the input's own border and ground rather
          than a Card: it is the drawer belonging to the field above it, and
          reading as a separate surface would break that. */}
      {open && (
        <div
          className={`absolute z-40 mt-1 w-full overflow-hidden ${inputSurfaceClass} shadow-xl`}
        >
          {suggestions.length > 0 && (
            <ul
              ref={listRef}
              id={listId}
              role="listbox"
              aria-label="Food suggestions"
              className="max-h-56 overflow-y-auto"
            >
              {suggestions.map((suggestion, index) => {
                const food = suggestion.kind === 'local' ? suggestion.food : suggestion.product
                const active = index === activeIndex
                return (
                  <li
                    key={suggestion.kind === 'local' ? `local-${suggestion.food.id}` : `off-${index}`}
                    id={optionId(index)}
                    role="option"
                    aria-selected={active}
                    // onMouseDown, not onClick: the panel closes on the
                    // document's mousedown, which would otherwise fire first
                    // and unmount the row before its click could land.
                    onMouseDown={(event) => {
                      event.preventDefault()
                      choose(suggestion)
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`flex cursor-pointer items-center justify-between px-3 py-2 text-left text-sm ${
                      active ? 'bg-slate-700' : ''
                    }`}
                  >
                    <span>
                      <span className="font-medium">{food.name}</span>
                      {suggestion.kind === 'off' && suggestion.product.brand && (
                        <span className="ml-2 text-xs text-ink-faint">
                          {suggestion.product.brand}
                        </span>
                      )}
                      <span className="ml-2 text-xs text-slate-400">{macroSummary(food)}</span>
                    </span>
                    {suggestion.kind === 'local' ? (
                      <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                        {suggestion.food.source === 'user' ? 'library' : 'OFF'}
                      </span>
                    ) : (
                      <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] uppercase text-sky-300">
                        OFF
                      </span>
                    )}
                  </li>
                )
              })}
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
          ) : null}

          {offError && (
            <p className="border-t border-slate-700 px-3 py-2 text-sm text-rose-400">{offError}</p>
          )}
        </div>
      )}
    </div>
  )
}
