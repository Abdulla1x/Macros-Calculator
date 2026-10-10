// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clockTime, weighInDue } from '../src/lib/weighIn.ts'

const base = { reminderTime: '07:30', cadence: 1, clock: '08:00', lastDate: '2026-10-09', today: '2026-10-10' }

test('due only with the reminder on and its time come', () => {
  assert.equal(weighInDue(base), true)
  assert.equal(weighInDue({ ...base, reminderTime: null }), false)
  assert.equal(weighInDue({ ...base, clock: '07:29' }), false)
  assert.equal(weighInDue({ ...base, clock: '07:30' }), true)
})

test('due once the last weigh-in is as old as the cadence', () => {
  assert.equal(weighInDue({ ...base, cadence: 3, lastDate: '2026-10-08' }), false)
  assert.equal(weighInDue({ ...base, cadence: 3, lastDate: '2026-10-07' }), true)
  assert.equal(weighInDue({ ...base, lastDate: null }), true)
})

test('the clock is zero-padded so it compares as text', () => {
  assert.equal(clockTime(new Date(2026, 9, 10, 7, 5)), '07:05')
  assert.equal(clockTime(new Date(2026, 9, 10, 19, 30)), '19:30')
})
