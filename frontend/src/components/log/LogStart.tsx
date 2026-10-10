import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import MealAnalyzer from '../MealAnalyzer'
import MealCodeInput from '../MealCodeInput'
import { localIsoDate } from '../../lib/dates'
import { NextIcon } from '@/ui/icons'
import DayChips from './DayChips'
import { logDate } from './logPanelUrl'
import { RecentMeals, SavedMeals } from './MealShortcuts'
import { useLogPanel } from './useLogPanel'

const ROW =
  'flex min-h-[52px] w-full items-center gap-3 py-2.5 text-left text-body hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

/** The Log panel's first screen (overhaul 0a): which day the meal is for, then
 *  the AI box first, because AI is the largest single way meals are logged,
 *  then saved and recent meals, which carry most of the rest, then the other
 *  ways in. */
export default function LogStart() {
  const { search } = useLocation()
  const { open, setDate } = useLogPanel()
  const [pasting, setPasting] = useState(false)

  const today = localIsoDate()
  const date = logDate(search) ?? today

  return (
    // minmax(0, 1fr): a grid column otherwise grows to its widest child's
    // unbreakable content, and one long food name then widened the whole panel
    // past the screen.
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      {/* "For" rather than a date field: the day travels in the address, so
          the by-hand form and a saved estimate land on it. */}
      <DayChips legend="For" value={date} onChange={(day) => setDate(day === today ? null : day)} />

      <MealAnalyzer
        alwaysOpen
        onApply={() => open('hand', { state: { fromEstimate: true } })}
      />

      <SavedMeals />
      <RecentMeals />

      <div className="divide-y divide-rule border-y border-rule">
        <button type="button" onClick={() => open('hand')} className={ROW}>
          <span className="flex-1">Enter it by hand</span>
          <NextIcon size={18} aria-hidden className="text-ink-2" />
        </button>
        {pasting ? (
          <div className="py-3">
            <MealCodeInput
              startOpen
              onCancel={() => setPasting(false)}
              onLoaded={(sharedMeal, sharedCode) => open('hand', { state: { sharedMeal, sharedCode } })}
            />
          </div>
        ) : (
          <button type="button" onClick={() => setPasting(true)} className={ROW}>
            <span className="flex-1">Paste a meal code</span>
            <NextIcon size={18} aria-hidden className="text-ink-2" />
          </button>
        )}
      </div>
    </div>
  )
}
