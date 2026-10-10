import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { mealTimeLabel } from '../../lib/today'
import type { Meal } from '../../types'
import { Button } from '@/ui/button'
import Block from '@/ui/block'
import { LogIcon, NextIcon } from '@/ui/icons'

/** The day's meals (DESIGN.md: Meal rows). Each row is time, name and detail,
 *  then kcal, and opens the meal's own screen, where Edit, Log it again,
 *  Share, Keep and Delete live: one 56px target per meal instead of three
 *  12px glyphs (UA-13). */
export default function MealList({
  meals,
  error,
  onRetry,
  isToday,
  showTimes,
  trackCarbs,
  trackFat,
  onLog,
  held,
}: {
  /** Null while the day is still loading. */
  meals: Meal[] | null
  error: string | null
  onRetry: () => void
  isToday: boolean
  showTimes: boolean
  trackCarbs: boolean
  trackFat: boolean
  onLog: () => void
  /** A meal being deleted, still undoable: drawn struck through in its own
   *  place, with Undo and the draining bar, and left out of the totals. */
  held?: { meal: Meal; folding: boolean; onUndo: () => void } | null
}) {
  if (meals === null && !error) {
    return (
      <Block label="Meals">
        <div aria-hidden="true" className="grid gap-2 py-1">
          {[0, 1, 2].map((key) => (
            <span key={key} className="h-12 rounded-control bg-track/60 motion-safe:animate-pulse" />
          ))}
        </div>
      </Block>
    )
  }
  const all = meals ?? []
  const list = all.filter((meal) => meal.id !== held?.meal.id)
  const total = list.reduce((sum, meal) => sum + meal.calories, 0)
  const times = list.map((meal) => mealTimeLabel(meal, showTimes))
  // One column for the time only when some row has one, so a list without
  // any does not carry an empty gutter.
  const timed = times.some((time) => time !== null)

  return (
    <Block
      label={list.length ? `Meals · ${list.length}` : 'Meals'}
      value={list.length ? `${Math.round(total).toLocaleString()} kcal` : undefined}
    >
      {error ? (
        <p role="alert" className="border-l-2 border-ink pl-3 text-small">
          {error}{' '}
          <button type="button" onClick={onRetry} className="font-semibold underline underline-offset-3">
            Retry
          </button>
        </p>
      ) : all.length === 0 ? (
        <div className="grid gap-2 py-1">
          {isToday ? (
            <>
              <p>
                <b className="font-semibold">Nothing logged yet.</b> Suspiciously disciplined.
              </p>
              <p className="text-small text-ink-2">
                Type what you ate with the grams, say it, or snap it. The AI works out the numbers; you check them.
              </p>
            </>
          ) : (
            <p className="text-small text-ink-2">Nothing logged on this day.</p>
          )}
          <div>
            <Button variant="secondary" onClick={onLog}>
              <LogIcon size={18} aria-hidden="true" />
              {isToday ? 'Log your first meal' : 'Log a meal for this day'}
            </Button>
          </div>
        </div>
      ) : (
        <ul className="divide-y divide-rule">
          {all.map((meal) => {
            if (meal.id === held?.meal.id)
              return <HeldRow key={meal.id} meal={meal} folding={held.folding} onUndo={held.onUndo} />
            const index = list.indexOf(meal)
            const detail = [
              `${Math.round(meal.protein)} g protein`,
              trackCarbs && meal.carbs !== null && `${Math.round(meal.carbs)} g carbs`,
              trackFat && meal.fat !== null && `${Math.round(meal.fat)} g fat`,
            ]
              .filter(Boolean)
              .join(' · ')
            return (
              <li key={meal.id}>
                <Link
                  to={`/day/${meal.date}/meal/${meal.id}`}
                  state={{ meal }}
                  className="flex min-h-14 items-center gap-3 py-2 text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
                >
                  {timed && (
                    <span className="min-w-[3.2em] shrink-0 text-small whitespace-nowrap text-ink-2 tabular-nums">{times[index]}</span>
                  )}
                  <span className="grid min-w-0 flex-1 gap-0.5">
                    <span className="truncate">{meal.name}</span>
                    <span className="truncate text-small text-ink-2">{detail}</span>
                  </span>
                  <span className="text-row-number tabular-nums">{Math.round(meal.calories).toLocaleString()}</span>
                  <NextIcon size={18} aria-hidden="true" className="shrink-0 text-ink-2" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Block>
  )
}

/** A deleted meal while Undo is still offered (DESIGN.md: Delete and Undo):
 *  its name struck through, Undo, and a bar draining over the window. Undo
 *  takes focus when it appears, since the user just asked for the deletion
 *  and is the one who might take it back. */
function HeldRow({ meal, folding, onUndo }: { meal: Meal; folding: boolean; onUndo: () => void }) {
  const undo = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    undo.current?.focus({ preventScroll: false })
  }, [])
  return (
    <li
      className={`relative flex items-center gap-3 overflow-hidden ${folding ? 'animate-fold' : 'min-h-14 py-2'}`}
    >
      <span className="min-w-0 flex-1 truncate text-ink-2">
        <span className="sr-only">Deleted: </span>
        <span className="animate-strike bg-[linear-gradient(currentColor,currentColor)] bg-[length:100%_1.5px] bg-[position:0_55%] bg-no-repeat">
          {meal.name}
        </span>
      </span>
      <Button
        ref={undo}
        variant="ghost"
        onClick={onUndo}
        disabled={folding}
        aria-label={`Undo deleting ${meal.name}`}
      >
        Undo
      </Button>
      <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-0.5 origin-left animate-drain bg-ink-2" />
    </li>
  )
}
