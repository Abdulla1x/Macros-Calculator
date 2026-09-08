import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { per100gSummary } from '../../lib/foodDensity'
import type { Food, FoodDuplicatePair } from '../../types'

/** "These two look like the same food" — shown above the library it is about.
 *
 * The library fills itself up without being asked: every Open Food Facts pick
 * is cached, every ticked ingredient is saved, every AI estimate can be. The
 * unique index blocks the exact case, so everything that survives is a *near*
 * duplicate under a name nobody chose to make match — and until now nothing
 * pointed at one.
 *
 * ⚠ IT NEVER ACTS ON ITS OWN. The server's judgement (app/duplicates.py) is a
 * heuristic with thresholds, so this panel argues rather than asserts: it puts
 * both rows in the same units, per 100 g, and lets the user read the evidence.
 * Every delete is theirs, behind the same confirm step the list below uses.
 *
 * Its own file because FoodLibrarySection is already the largest section on the
 * page, and Phase 16 exists because that file grew.
 */

/** Dismissed pairs, per device.
 *
 * localStorage rather than a column, because this is a note about the UI, not
 * about the data: "I know, I want both." A table for it would need a migration,
 * a CASCADE and an isolation test to record a preference that stops mattering
 * the moment either row is edited.
 *
 * Every access is wrapped — a private window, cleared site data or a browser
 * set to block storage all throw here, and none of them should cost the user
 * the panel itself.
 */
const DISMISSED_KEY = 'macros.dismissedFoodDuplicates'

/** Order-independent, so a pair cannot be dismissed once and come back because
 *  the server happened to report its two ids the other way round. */
const pairKey = (pair: FoodDuplicatePair) =>
  [pair.a_id, pair.b_id].sort((a, b) => a - b).join('-')

function readDismissed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(DISMISSED_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

/** Written back pruned to the pairs the server still reports.
 *
 * Without this the list only ever grows: a dismissal for two foods that were
 * deleted years ago is dead weight that can never be reached again, and the
 * key would accumulate one entry per pair the user ever waved off. */
function writeDismissed(keys: Set<string>, live: FoodDuplicatePair[]) {
  const liveKeys = new Set(live.map(pairKey))
  try {
    window.localStorage.setItem(
      DISMISSED_KEY,
      JSON.stringify([...keys].filter((key) => liveKeys.has(key))),
    )
  } catch {
    /* A device that cannot remember the dismissal still honours it this
       session; the panel simply returns next time. */
  }
}

export default function DuplicateFoodsPanel({
  foods,
  onChanged,
}: {
  /** The library as the section already has it. Pairs are ids into this, so a
   *  row deleted here stops rendering with no second request. */
  foods: Food[]
  /** Reload the library after a delete. */
  onChanged: () => void
}) {
  const [pairs, setPairs] = useState<FoodDuplicatePair[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(readDismissed)
  const [confirming, setConfirming] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Refetched whenever the library changes identity, which the section does on
  // every save and delete. An edit can make a pair stop being a duplicate, and
  // a panel still showing it would be arguing from numbers that are on screen
  // directly underneath and no longer agree.
  useEffect(() => {
    let stale = false
    api
      .getFoodDuplicates()
      .then((next) => {
        if (stale) return
        setPairs(next)
        setError('')
      })
      // Silent: this is an unasked-for extra on a page that works without it,
      // and an error banner for a suggestion nobody requested is worse than no
      // suggestion.
      .catch(() => {
        if (!stale) setPairs([])
      })
    return () => {
      stale = true
    }
  }, [foods])

  const byId = useMemo(() => new Map(foods.map((food) => [food.id, food])), [foods])

  // A pair renders only when BOTH rows are still in the library. That is what
  // makes deleting one of them enough to close the card, with no refetch and no
  // special case.
  const visible = useMemo(
    () =>
      pairs
        .filter((pair) => !dismissed.has(pairKey(pair)))
        .map((pair) => ({
          key: pairKey(pair),
          a: byId.get(pair.a_id),
          b: byId.get(pair.b_id),
        }))
        .filter(
          (pair): pair is { key: string; a: Food; b: Food } =>
            pair.a !== undefined && pair.b !== undefined,
        ),
    [pairs, dismissed, byId],
  )

  const dismiss = useCallback(
    (key: string) => {
      setDismissed((current) => {
        const next = new Set(current).add(key)
        writeDismissed(next, pairs)
        return next
      })
    },
    [pairs],
  )

  const remove = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteFood(id)
      setConfirming(null)
      setError('')
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that — try again.')
    } finally {
      setBusy(false)
    }
  }

  // No pairs, no panel. Not a "nothing to review" placeholder: a library with
  // no duplicates is the normal case, and announcing it every visit would make
  // the section noisier for everyone it has nothing to tell.
  if (visible.length === 0) return null

  return (
    <section
      aria-label="Possible duplicate foods"
      className="mb-4 rounded-card border border-amber-500/40 bg-amber-500/10 p-3"
    >
      <h3 className="text-sm font-semibold text-amber-200">
        <span aria-hidden="true">👀</span>{' '}
        {visible.length === 1
          ? 'Two of your foods look like the same thing'
          : `${visible.length} pairs of your foods look like the same thing`}
      </h3>
      <p className="mt-1 text-xs text-ink-muted">
        Shown per 100 g so they can be compared — each is normally saved against
        its own serving size. Keep whichever is right, or keep both.
      </p>

      <ul className="mt-3 space-y-3">
        {visible.map(({ key, a, b }) => (
          <li key={key} className="rounded-control border border-amber-500/30 p-2">
            <ul>
              {[a, b].map((food) => (
                <li
                  key={food.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1 text-sm"
                >
                  <span className="font-medium text-ink">{food.name}</span>
                  <span className="text-xs text-ink-muted">{per100gSummary(food)}</span>
                  <span className="ml-auto flex items-center gap-2 text-xs">
                    {confirming === food.id ? (
                      <>
                        <button
                          onClick={() => remove(food.id)}
                          disabled={busy}
                          className="rounded border border-rose-500/50 bg-rose-500/10 px-2 py-0.5 text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
                        >
                          Delete for good
                        </button>
                        <button
                          onClick={() => setConfirming(null)}
                          className="text-ink-muted hover:text-ink"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirming(food.id)}
                        disabled={busy}
                        aria-label={`Delete ${food.name}`}
                        className="text-ink-muted hover:text-rose-400 disabled:opacity-40"
                      >
                        Delete
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <button
              onClick={() => dismiss(key)}
              className="mt-1 text-xs text-ink-muted underline hover:text-ink"
            >
              Not a duplicate — stop asking
            </button>
          </li>
        ))}
      </ul>

      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
    </section>
  )
}
