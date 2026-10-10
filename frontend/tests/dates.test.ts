// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { shortDate } from '../src/lib/dates.ts'

const now = new Date(2026, 9, 11)

test('a date this year reads as month and day', () => {
  assert.equal(shortDate('2026-09-28', now, 'en-US'), 'Sep 28')
  assert.equal(shortDate('2026-01-02', now, 'en-US'), 'Jan 2')
})

test('a date from another year carries its year', () => {
  assert.equal(shortDate('2025-12-31', now, 'en-US'), 'Dec 31, 2025')
})

test('the day is the calendar day written, not the UTC one', () => {
  // parseIsoDate builds local midnight; new Date(iso) would be UTC and read
  // as the day before anywhere west of Greenwich.
  assert.equal(shortDate('2026-03-01', now, 'en-US'), 'Mar 1')
})

test('it follows the language it is given', () => {
  assert.equal(shortDate('2026-09-28', now, 'en-GB'), '28 Sept')
})

test('anything that is not a YYYY-MM-DD date is refused', () => {
  assert.throws(() => shortDate('09-28', now, 'en-US'))
})
