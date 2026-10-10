import type { WeeklyReview } from '../types.ts'
import { parseIsoDate } from './dates.ts'

/** The review card's day (decided 2026-10-10: Monday, the first day after a
 *  full Monday-to-Sunday week). The review itself can be opened on any day;
 *  this only decides when Today brings it up. A setting for it is phase 3. */
export function isReviewDay(today: string): boolean {
  return parseIsoDate(today).getDay() === 1
}

/** One plain sentence for the card, from the review's own checks. Nothing to
 *  fix gets the wry line (DESIGN.md: Voice); anything else just counts, and
 *  the review page says what and why. */
export function reviewHeadline(review: WeeklyReview): string {
  if (review.logged_days === 0) return 'No meals logged last week, so there is nothing to review yet.'
  const judged = review.checks.filter((check) => check.status === 'on_track' || check.status === 'off_track')
  const off = judged.filter((check) => check.status === 'off_track').length
  const days = `${review.logged_days} of 7 days logged`
  if (judged.length === 0) return `${days}.`
  if (off === 0) return `${days}. Nothing to fix this week. Carry on.`
  return `${days}. ${off} of ${judged.length} ${judged.length === 1 ? 'check is' : 'checks are'} off target.`
}
