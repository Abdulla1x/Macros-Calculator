import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Meal } from '../types'

/** How long Undo is offered (DESIGN.md: Delete and Undo). */
export const UNDO_MS = 10_000
/** How long the line takes to fold closed once it is gone (index.css). */
const FOLD_MS = 280

/** A meal deletion held back for UNDO_MS before it reaches the server.
 *
 *  The server has no "restore": a deleted meal is gone. Deleting at once and
 *  having Undo re-create the meal would bring back a copy, with a new id, at
 *  the bottom of the list, and without its link to the AI estimate it came
 *  from (owner, 2026-10-10: hold it instead). So nothing is sent until the
 *  window ends, and Undo simply cancels.
 *
 *  The window also ends early, and the delete is sent, when the page that
 *  holds it goes away or the app goes to the background: a deletion the user
 *  walked away from must still happen, and a phone may never come back to
 *  this tab to finish a timer. */
export function useHeldDelete(onSettled: (error: string | null) => void) {
  const [held, setHeld] = useState<{ meal: Meal; folding: boolean } | null>(null)
  // Sent, and not to be counted again unless the server refuses: the held
  // state ends when the line has folded, which is before the reload that drops
  // the meal has come back (lib/today.ts, shownMeals).
  const [gone, setGone] = useState<ReadonlySet<number>>(() => new Set())
  const heldRef = useRef<Meal | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const settled = useRef(onSettled)
  useEffect(() => {
    settled.current = onSettled
  })

  const send = useCallback((meal: Meal) => {
    window.clearTimeout(timer.current)
    heldRef.current = null
    // Gone now: the line folds closed, then leaves.
    setGone((ids) => new Set(ids).add(meal.id))
    setHeld({ meal, folding: true })
    window.setTimeout(() => setHeld((now) => (now?.meal.id === meal.id && now.folding ? null : now)), FOLD_MS)
    api
      .deleteMeal(meal.id)
      .then(() => settled.current(null))
      .catch(() => {
        // Not deleted, so it counts again: the totals must not claim otherwise.
        setGone((ids) => {
          const next = new Set(ids)
          next.delete(meal.id)
          return next
        })
        settled.current(`"${meal.name}" wasn't deleted. Check your connection, then try again.`)
      })
  }, [])

  /** Forgets the gone ids a fresh answer no longer contains: the server has
   *  caught up with them, and nothing should hide a later meal on their
   *  account. */
  const prune = useCallback((meals: readonly Meal[]) => {
    setGone((ids) => {
      if (ids.size === 0) return ids
      const present = new Set(meals.map((meal) => meal.id))
      const next = new Set([...ids].filter((id) => present.has(id)))
      return next.size === ids.size ? ids : next
    })
  }, [])

  const hold = useCallback(
    (meal: Meal) => {
      // One at a time: a second deletion settles the first.
      if (heldRef.current && heldRef.current.id !== meal.id) send(heldRef.current)
      window.clearTimeout(timer.current)
      heldRef.current = meal
      setHeld({ meal, folding: false })
      timer.current = window.setTimeout(() => send(meal), UNDO_MS)
    },
    [send],
  )

  const undo = useCallback(() => {
    window.clearTimeout(timer.current)
    heldRef.current = null
    setHeld(null)
  }, [])

  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    const away = () => {
      if (document.visibilityState === 'hidden' && heldRef.current) send(heldRef.current)
    }
    document.addEventListener('visibilitychange', away)
    return () => {
      mounted.current = false
      document.removeEventListener('visibilitychange', away)
      // Leaving the page: send it now rather than lose it. A tick later, and
      // only if nothing mounted again in between: React's development mode
      // unmounts and remounts every effect once on purpose, and that rehearsal
      // must not delete anything.
      window.setTimeout(() => {
        if (!mounted.current && heldRef.current) send(heldRef.current)
      }, 0)
    }
  }, [send])

  return { held, gone, hold, undo, prune }
}
