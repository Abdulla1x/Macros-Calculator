import { daysBetween } from './dates.ts'

/** "HH:MM" in the browser's own timezone. The API stores no timezone for
 *  anyone, so only the browser can say whether the reminder time has come. */
export function clockTime(now: Date): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

/** Whether today's weigh-in card says "Due today".
 *
 *  The weigh-in reminder's rule, unchanged from the banner it replaces: only
 *  with the reminder switched on, only once its time has come, and only when
 *  the last weigh-in is at least `cadence` days old (or there is none in the
 *  window). With the reminder off the card is simply there, and says nothing
 *  about being due. "HH:MM" strings compare correctly as text. */
export function weighInDue({
  reminderTime,
  cadence,
  clock,
  lastDate,
  today,
}: {
  reminderTime: string | null
  cadence: number
  clock: string
  lastDate: string | null
  today: string
}): boolean {
  if (reminderTime === null || clock < reminderTime) return false
  return lastDate === null || daysBetween(lastDate, today) >= cadence
}
