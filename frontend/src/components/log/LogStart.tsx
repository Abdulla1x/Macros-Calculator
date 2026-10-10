import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import MealAnalyzer from '../MealAnalyzer'
import MealCodeInput from '../MealCodeInput'
import { addDays, localIsoDate, parseIsoDate } from '../../lib/dates'
import { useSettings } from '../../settings/SettingsContext'
import { Chip } from '@/ui/chip'
import { NextIcon } from '@/ui/icons'
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
  const { settings } = useSettings()
  const { open, setDate } = useLogPanel()
  const [pasting, setPasting] = useState(false)

  const today = localIsoDate()
  const yesterday = addDays(today, -1)
  const date = logDate(search) ?? today
  const other = date !== today && date !== yesterday
  const chipDate = parseIsoDate(date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

  return (
    <div className="grid gap-5">
      {/* "For" rather than a date field: nearly every meal is today's or
          yesterday's, so those are one tap, and anything older is the native
          picker behind "Other day". */}
      <fieldset className="grid gap-2">
        <legend className="mb-2 text-field-label text-ink-2">For</legend>
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip pressed={date === today} onClick={() => setDate(null)}>
            Today
          </Chip>
          <Chip pressed={date === yesterday} onClick={() => setDate(yesterday)}>
            Yesterday
          </Chip>
          <label
            className={`relative inline-flex h-9 items-center rounded-control border-[1.5px] px-3 text-[13.5px] font-semibold focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-action ${
              other ? 'border-ink bg-ink text-ground' : 'border-rule text-ink hover:border-ink'
            }`}
          >
            {other ? chipDate : 'Other day'}
            {/* The native picker, laid invisibly over the chip: on a phone it
                opens the system calendar, which beats any picker drawn here. */}
            <input
              type="date"
              // Contains the words on the chip, so a voice command naming what
              // is on screen finds it (WCAG 2.5.3, label in name).
              aria-label={other ? `${chipDate}, pick another day` : 'Other day'}
              value={date}
              max={today}
              onChange={(event) => event.target.value && setDate(event.target.value === today ? null : event.target.value)}
              className="absolute inset-0 cursor-pointer opacity-0"
            />
          </label>
        </div>
      </fieldset>

      <MealAnalyzer
        settings={settings}
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
