import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useLiveMessage } from '../../hooks/useLiveMessage'
import { addDays } from '../../lib/dates'
import { MAX_WEIGH_IN_REMINDER_DAYS } from '../../lib/limits'
import { displayToKg, formatWeight, unitLabel } from '../../lib/units'
import { clockTime, weighInDue } from '../../lib/weighIn'
import { useSettings } from '../../settings/SettingsContext'
import type { WeightEntry } from '../../types'
import { Button } from '@/ui/button'
import { FIELD } from '@/ui/field'
import { cn } from '@/lib/utils'
import { WeighInIcon } from '@/ui/icons'
import Tracker from './Tracker'

/** How often the clock is re-read while waiting for the reminder time, so a
 *  20:00 reminder appears at 20:00 on a page opened at 19:58. */
const CLOCK_TICK_MS = 60_000

/** The weigh-in, as a card on Today (0a: Weight is split; the weigh-in is a
 *  daily thing, so it lives here, and the trend lives in Progress).
 *
 *  It carries the weigh-in reminder: "Due today" appears on the card when the
 *  reminder's own rule says so (lib/weighIn.ts), which replaces the banner
 *  that used to sit on every page. With the reminder off, the card is simply
 *  there. It follows the day on show, and a weigh-in is editable here: the
 *  server keeps one per day, so saving again replaces it. */
export default function WeighInCard({ day, today }: { day: string; today: string }) {
  const { settings, reload: reloadSettings } = useSettings()
  const unit = settings?.weight_unit ?? 'kg'
  const label = unitLabel(unit)
  const [entries, setEntries] = useState<WeightEntry[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [clock, setClock] = useState(() => clockTime(new Date()))
  useLiveMessage(error)

  // A window, not the whole log: the reminder's cadence is at most
  // MAX_WEIGH_IN_REMINDER_DAYS, so one day past it is all the rule can need.
  const load = useCallback(() => {
    api
      .getWeights(addDays(day, -(MAX_WEIGH_IN_REMINDER_DAYS + 1)), day)
      .then((next) => {
        setEntries(next)
        setFailed(false)
      })
      .catch(() => setFailed(true))
  }, [day])
  useEffect(load, [load])

  // Each day starts unedited, with nothing said yet.
  useEffect(() => {
    setEditing(false)
    setNote(null)
    setError(null)
  }, [day])

  const reminderTime = settings?.weigh_in_reminder_time ?? null
  useEffect(() => {
    const refresh = () => setClock(clockTime(new Date()))
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    // Ticks only while the reminder time is still ahead.
    const tick = reminderTime !== null && clock < reminderTime ? window.setInterval(refresh, CLOCK_TICK_MS) : undefined
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
      window.clearInterval(tick)
    }
  }, [reminderTime, clock])

  // Oldest first from the server.
  const entry = entries?.find((each) => each.date === day) ?? null
  const latest = entries && entries.length > 0 ? entries[entries.length - 1]! : null
  const due =
    day === today &&
    entries !== null &&
    entry === null &&
    weighInDue({
      reminderTime,
      cadence: settings?.weigh_in_reminder_days ?? 1,
      clock,
      lastDate: latest?.date ?? null,
      today,
    })

  const showInput = entries !== null && (entry === null || editing)
  // Prefilled with the most recent weight: the next one is usually close to
  // it, so this is a nudge, not a default that hides a typo.
  const prefill = entry ?? latest
  useEffect(() => {
    if (showInput) setValue(prefill ? formatWeight(prefill.weight_kg, unit) : '')
    // Seeds the field when it appears, and again once the unit is known (the
    // weigh-ins can arrive before the settings do). Nothing else re-seeds it,
    // so it never fights the user as they type.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInput, day, unit])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    const typed = Number(value.replace(',', '.'))
    if (!value.trim() || !Number.isFinite(typed) || typed <= 0) {
      setError(`Enter your weight in ${label}.`)
      return
    }
    const first = entries !== null && entries.length === 0
    setSaving(true)
    setError(null)
    try {
      await api.saveWeight({ date: day, weight_kg: displayToKg(typed, unit) })
      setEditing(false)
      setNote(first ? 'First weigh-in. Your trend line starts now.' : 'Saved.')
      load()
      // With "work out my goals" on, a weigh-in rewrites the daily targets on
      // the server; refetch them so the calories band follows at once.
      reloadSettings()
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't save. Check your connection, then try again.")
    } finally {
      setSaving(false)
    }
  }

  const figure = entry ? (
    <>
      <span className="font-semibold">
        {formatWeight(entry.weight_kg, unit)} {label}
      </span>
      {!editing && (
        <Button variant="ghost" className="h-9 px-3" onClick={() => setEditing(true)} aria-label={`Edit this weigh-in, ${formatWeight(entry.weight_kg, unit)} ${label}`}>
          Edit
        </Button>
      )}
    </>
  ) : due ? (
    <span className="font-semibold text-action">Due today</span>
  ) : undefined

  return (
    <Tracker icon={<WeighInIcon size={22} />} title="Weigh-in" value={figure}>
      {failed && (
        <p role="alert" className="border-l-2 border-ink pl-3 text-small">
          Couldn't load your weigh-ins.{' '}
          <button type="button" onClick={load} className="font-semibold underline underline-offset-3">
            Retry
          </button>
        </p>
      )}
      {showInput && (
        <form onSubmit={save} className="flex flex-wrap items-center gap-2">
          <input
            inputMode="decimal"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-label={`Weight in ${label === 'kg' ? 'kilograms' : 'pounds'}`}
            aria-invalid={error !== null || undefined}
            className={cn(FIELD, 'w-28 text-[19px] font-bold [font-stretch:85%] tabular-nums')}
          />
          <span className="text-ink-2">{label}</span>
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
          {editing && (
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          )}
        </form>
      )}
      {error && (
        <p role="alert" className="border-l-2 border-ink pl-3 text-small">
          {error}
        </p>
      )}
      <p role="status" className="text-small text-ink-2 empty:hidden">
        {note}
      </p>
    </Tracker>
  )
}
