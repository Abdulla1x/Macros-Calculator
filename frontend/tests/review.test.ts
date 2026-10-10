// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isReviewDay, reviewHeadline } from '../src/lib/review.ts'
import type { ReviewCheck, WeeklyReview } from '../src/types.ts'

const check = (status: ReviewCheck['status']): ReviewCheck => ({
  key: 'x',
  status,
  value: null,
  target: null,
  unit: '',
  sample_days: 7,
  detail: '',
  unavailable_reason: null,
})
const review = (logged: number, statuses: ReviewCheck['status'][]): WeeklyReview => ({
  window_start: '2026-10-05',
  window_end: '2026-10-11',
  logged_days: logged,
  checks: statuses.map(check),
})

test('the card comes up on Mondays only', () => {
  assert.equal(isReviewDay('2026-10-12'), true)
  assert.equal(isReviewDay('2026-10-10'), false)
  assert.equal(isReviewDay('2026-10-11'), false)
})

test('the headline counts what is off, and only judged checks', () => {
  assert.equal(reviewHeadline(review(7, ['on_track', 'on_track', 'note'])), '7 of 7 days logged. Nothing to fix this week. Carry on.')
  assert.equal(reviewHeadline(review(5, ['on_track', 'off_track', 'unknown'])), '5 of 7 days logged. 1 of 2 checks are off target.')
  assert.equal(reviewHeadline(review(3, ['off_track'])), '3 of 7 days logged. 1 of 1 check is off target.')
  assert.equal(reviewHeadline(review(2, ['unknown', 'note'])), '2 of 7 days logged.')
  assert.match(reviewHeadline(review(0, [])), /nothing to review yet/)
})
