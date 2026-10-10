import { addDays } from '../../lib/dates'
import { dayHeading } from '../../lib/today'
import { BackIcon, NextIcon } from '@/ui/icons'

const STEP =
  'grid size-11 shrink-0 place-items-center rounded-control text-ink hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action disabled:pointer-events-none disabled:opacity-30'

/** Today's one date control (UA-18): back a day, the day's name, forward a
 *  day. Tapping the name opens the phone's own calendar, through a native date
 *  input laid invisibly over it, the same way the Log panel's "Other day" chip
 *  does. There is no "jump to today": the Today tab is that, since it always
 *  leads to the address without a day. Never later than today. */
export default function DateBar({
  day,
  today,
  onChange,
}: {
  day: string
  today: string
  onChange: (day: string) => void
}) {
  const heading = dayHeading(day, today, addDays(today, -1))
  return (
    <div className="flex items-center justify-between gap-2 border-b border-rule pb-1.5">
      <button type="button" className={STEP} onClick={() => onChange(addDays(day, -1))} aria-label="Previous day">
        <BackIcon size={22} />
      </button>
      <div className="relative min-w-0 rounded-control px-2 py-2 hover:bg-ink/5 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-action">
        <h1 className="truncate text-title">{heading}</h1>
        <input
          type="date"
          value={day}
          max={today}
          onChange={(event) => event.target.value && onChange(event.target.value)}
          // Contains the words on screen, so a voice command naming what is
          // shown finds it (WCAG 2.5.3, label in name).
          aria-label={`${heading}, pick another day`}
          className="absolute inset-0 size-full cursor-pointer opacity-0"
        />
      </div>
      <button
        type="button"
        className={STEP}
        onClick={() => onChange(addDays(day, 1))}
        disabled={day >= today}
        aria-label="Next day"
      >
        <NextIcon size={22} />
      </button>
    </div>
  )
}
