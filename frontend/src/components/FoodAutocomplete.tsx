import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Food, FoodCreate, OFFProduct, ReferenceFood } from '../types'
import { SOURCE_BADGE, SOURCE_NAME } from '../lib/foodSources'
import { FIELD } from '@/ui/field'
import { useLiveMessage } from '../hooks/useLiveMessage'

interface Props {
  value: string
  onChange: (name: string) => void
  /** `fromLibrary` is true only for a row from the user's own library. A food
   *  from a table or Open Food Facts is NOT saved by picking it; LogMeal offers
   *  the "save to library" tick for it instead, unticked. */
  onSelect: (food: FoodCreate, fromLibrary: boolean) => void
}

/** One row of the suggestion list, from any of the three sources.
 *
 * The lists are FLATTENED into a single array rather than kept apart, and
 * that is what makes the keyboard work. ARIA's combobox pattern moves a single
 * cursor through one listbox; separate lists would need either several cursors
 * or a group structure, and every row already carries a badge saying where it
 * came from -- so the grouping is visible without being structural. */
type Suggestion =
  | { kind: 'local'; food: Food }
  | { kind: 'reference'; food: ReferenceFood }
  | { kind: 'off'; product: OFFProduct }

/**
 * Type-ahead food search, in three tiers: the user's own library, then generic
 * foods from the imported national tables (USDA, UK, France, Australia,
 * Canada), both as you type; then Open Food Facts for packaged products, on
 * request, because it is a slow third-party call with a shared rate limit.
 *
 * Picking a table or OFF row does NOT save it to the library any more (decided
 * 2026-10-06): the tables are searched instantly anyway, and the library is
 * meant to hold foods the user chose. LogMeal offers the tick instead.
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
  const [referenceResults, setReferenceResults] = useState<ReferenceFood[]>([])
  const [offResults, setOffResults] = useState<OFFProduct[] | null>(null)
  const [offLoading, setOffLoading] = useState(false)
  const [offError, setOffError] = useState<string | null>(null)
  useLiveMessage(offError)
  // UA-22: Open Food Facts rows land at the END of the list, under the library
  // and the tables, so with six or more matches above them they arrived below
  // the fold, and the only sign anything happened was the button vanishing; a
  // screen reader heard nothing at all. Now the count is said, on screen and
  // aloud, and the first of them is scrolled into view (effect below).
  const offNotice =
    offResults && offResults.length > 0
      ? `${offResults.length} ${offResults.length === 1 ? 'result' : 'results'} from Open Food Facts`
      : null
  useLiveMessage(offNotice)
  // -1 is "no row is current", which is the state the panel opens in. Typing a
  // name and pressing Enter must submit what was typed, not silently swap in
  // whatever happened to be first in a list the user has not looked at.
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const skipNextSearch = useRef(false)
  // Stable across renders and unique per instance -- LogMeal renders one of
  // these per ingredient row, so a hard-coded id would repeat down the page and
  // aria-activedescendant would resolve to the first one every time.
  const listId = useId()
  const optionId = (index: number) => `${listId}-option-${index}`

  const suggestions: Suggestion[] = [
    ...localResults.map((food): Suggestion => ({ kind: 'local', food })),
    ...referenceResults.map((food): Suggestion => ({ kind: 'reference', food })),
    ...(offResults ?? []).map((product): Suggestion => ({ kind: 'off', product })),
  ]

  useEffect(() => {
    if (skipNextSearch.current) {
      skipNextSearch.current = false
      return
    }
    if (value.trim().length < 2) {
      setLocalResults([])
      setReferenceResults([])
      setOffResults(null)
      return
    }
    // `stale` stops a slow response for a previous query from overwriting the
    // current results (the timer only guards the debounce, not the fetch).
    let stale = false
    const timer = setTimeout(() => {
      const query = value.trim()
      // Both at once, and settled rather than all: either list is worth
      // showing without the other, so one failing must not blank both.
      void Promise.allSettled([api.searchFoods(query), api.searchReferenceFoods(query)]).then(
        ([local, reference]) => {
          if (stale) return
          setLocalResults(local.status === 'fulfilled' ? local.value : [])
          setReferenceResults(reference.status === 'fulfilled' ? reference.value : [])
          setOffResults(null)
          setOffError(null)
          // Only while the user is in the field. The form also fills names
          // itself -- a saved meal, a copied meal, an AI estimate -- and a
          // list opening on its own then covered the very form it was filling.
          // Focusing the field later reopens it (onFocus below).
          setOpen(document.activeElement === inputRef.current)
        },
      )
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
  }, [localResults, referenceResults, offResults])

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

  // Bring the first Open Food Facts row into view when they arrive. "nearest"
  // scrolls the list only as far as needed, and never the page around it.
  const firstOffIndex = localResults.length + referenceResults.length
  useEffect(() => {
    if (!offResults || offResults.length === 0) return
    listRef.current
      ?.querySelector(`#${CSS.escape(optionId(firstOffIndex))}`)
      ?.scrollIntoView({ block: 'nearest' })
    // Only when a new set of results arrives; optionId is derived from a
    // stable id, and the index is fixed for that set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offResults])

  const pick = (food: FoodCreate, fromLibrary: boolean) => {
    skipNextSearch.current = true
    onSelect(food, fromLibrary)
    setOpen(false)
    setOffResults(null)
    setActiveIndex(-1)
  }

  /** Every source goes through here, so keyboard and mouse cannot diverge --
   *  and all inherit skipNextSearch, which is what stops the name written
   *  back into the input from re-opening the panel it just closed.
   *
   *  Nothing is saved: an OFF pick used to be cached in the library here, and
   *  that is what was turned off (see the component's docstring). */
  const choose = (suggestion: Suggestion) => {
    if (suggestion.kind === 'local') {
      pick(suggestion.food, true)
      return
    }
    const { name, serving_size, calories, protein, carbs, fat, source } =
      suggestion.kind === 'reference' ? suggestion.food : suggestion.product
    pick({ name, serving_size, calories, protein, carbs, fat, source }, false)
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

  const macroSummary = (food: FoodCreate | OFFProduct | ReferenceFood) =>
    `${food.calories} kcal · ${food.protein} g protein / ${food.serving_size} g`

  const listboxOpen = open && suggestions.length > 0

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => value.trim().length >= 2 && setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Type a food name…"
        aria-label="Food name"
        className={FIELD}
        role="combobox"
        aria-expanded={listboxOpen}
        aria-controls={listboxOpen ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={
          listboxOpen && activeIndex >= 0 ? optionId(activeIndex) : undefined
        }
      />
      {/* The drawer belonging to the field above: the field's ground, with an
          ink border rather than a shadow to stand it apart from the page (the
          Flat Rule). */}
      {open && (
        <div className="absolute z-40 mt-1 w-full overflow-hidden rounded-control border-[1.5px] border-ink bg-field">
          {suggestions.length > 0 && (
            <ul
              ref={listRef}
              id={listId}
              role="listbox"
              aria-label="Food suggestions"
              className="max-h-64 overflow-y-auto"
            >
              {suggestions.map((suggestion, index) => {
                const food = suggestion.kind === 'off' ? suggestion.product : suggestion.food
                const active = index === activeIndex
                const key =
                  suggestion.kind === 'local' ? `local-${suggestion.food.id}` : `${suggestion.kind}-${index}`
                return (
                  <li
                    key={key}
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
                    className={`flex min-h-11 cursor-pointer items-center justify-between gap-3 border-b border-rule px-3 py-2 text-left last:border-b-0 ${
                      active ? 'bg-ink/10' : ''
                    }`}
                  >
                    <span className="grid min-w-0">
                      <span className="truncate text-body">
                        {food.name}
                        {suggestion.kind === 'off' && suggestion.product.brand && (
                          <span className="ml-2 text-small text-ink-2">{suggestion.product.brand}</span>
                        )}
                      </span>
                      <span className="text-small text-ink-2 tabular-nums">{macroSummary(food)}</span>
                    </span>
                    {/* The fact colour for the user's own foods (DESIGN.md: it
                        marks values from their saved foods), plain ink 2 for
                        everyone else's: the first question is "is this mine?",
                        the second "whose figures are these?". The visible tag
                        is a short code; the full name goes to screen readers,
                        for whom "FR" alone says little. */}
                    {suggestion.kind === 'local' ? (
                      <span className="shrink-0 rounded-tag border-[1.5px] border-fact px-1.5 text-[11px] font-bold tracking-[0.04em] text-fact uppercase">
                        <span aria-hidden="true">
                          {suggestion.food.source === 'user' ? 'library' : SOURCE_BADGE[suggestion.food.source]}
                        </span>
                        <span className="sr-only">
                          {suggestion.food.source === 'user'
                            ? 'your library'
                            : `your library, from ${SOURCE_NAME[suggestion.food.source]}`}
                        </span>
                      </span>
                    ) : (
                      <span className="shrink-0 rounded-tag border-[1.5px] border-ink-2 px-1.5 text-[11px] font-bold tracking-[0.04em] text-ink-2 uppercase">
                        <span aria-hidden="true">{SOURCE_BADGE[food.source]}</span>
                        <span className="sr-only">{SOURCE_NAME[food.source]}</span>
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
              className="min-h-11 w-full border-t border-rule px-3 py-2 text-left text-small font-semibold text-action underline underline-offset-3 hover:bg-ink/5 disabled:opacity-45"
            >
              {offLoading
                ? 'Searching Open Food Facts…'
                : suggestions.length === 0
                  ? `No "${value.trim()}" found — search packaged products (Open Food Facts)`
                  : 'Packaged product? Search Open Food Facts'}
            </button>
          ) : offResults.length === 0 ? (
            <p className="border-t border-rule px-3 py-2 text-small text-ink-2">
              No packaged products found on Open Food Facts. Enter the numbers below.
            </p>
          ) : (
            <p className="border-t border-rule px-3 py-2 text-small text-ink-2">
              {offNotice}, at the end of the list.
            </p>
          )}

          {/* Ink and words, never red (DESIGN.md, the No Red Rule). */}
          {offError && <p className="border-t border-rule px-3 py-2 text-small">{offError}</p>}
        </div>
      )}
    </div>
  )
}
