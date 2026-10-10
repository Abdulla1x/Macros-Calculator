import { addDays, localIsoDate, parseIsoDate } from '../../lib/dates'
import { Chip } from '@/ui/chip'

/** Which day a meal is for: Today, Yesterday, or the native date picker behind
 *  "Other day" (UA-18: one control for one value, where the form used to show
 *  steppers, a date box and chips at once). Nearly every meal is today's or
 *  yesterday's, so those are one tap; on a phone, the picker opens the system
 *  calendar, which beats any calendar drawn here. Never later than today. */
export default function DayChips({
  legend,
  value,
  onChange,
}: {
  legend: string
  value: string
  onChange: (date: string) => void
}) {
  const today = localIsoDate()
  const yesterday = addDays(today, -1)
  const other = value !== today && value !== yesterday
  const chipDate = parseIsoDate(value).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-field-label text-ink-2">{legend}</legend>
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip pressed={value === today} onClick={() => onChange(today)}>
          Today
        </Chip>
        <Chip pressed={value === yesterday} onClick={() => onChange(yesterday)}>
          Yesterday
        </Chip>
        <label
          className={`relative inline-flex h-9 items-center rounded-control border-[1.5px] px-3 text-[13.5px] font-semibold focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-action ${
            other ? 'border-ink bg-ink text-ground' : 'border-rule text-ink hover:border-ink'
          }`}
        >
          {other ? chipDate : 'Other day'}
          {/* The native picker, laid invisibly over the chip. */}
          <input
            type="date"
            // Contains the words on the chip, so a voice command naming what
            // is on screen finds it (WCAG 2.5.3, label in name).
            aria-label={other ? `${chipDate}, pick another day` : 'Other day'}
            value={value}
            max={today}
            onChange={(event) => event.target.value && onChange(event.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
      </div>
    </fieldset>
  )
}
