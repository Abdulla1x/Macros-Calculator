// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { logDate, logDepth, logScreen, withLog, withoutLog } from '../src/components/log/logPanelUrl.ts'

test('the panel is open only when the flag is present', () => {
  assert.equal(logScreen(''), null)
  assert.equal(logScreen('?date=2026-10-10'), null)
  assert.equal(logScreen('?log'), 'start')
  assert.equal(logScreen('?log='), 'start')
  assert.equal(logScreen('?log=hand'), 'hand')
  assert.equal(logScreen('?log=anything'), 'start')
})

test('opening keeps the page’s own parameters and writes a bare flag', () => {
  assert.equal(withLog('', 'start'), '?log')
  assert.equal(withLog('?tab=2', 'start'), '?tab=2&log')
  assert.equal(withLog('?log', 'hand'), '?log=hand')
  assert.equal(withLog('', 'start', '2026-10-09'), '?log&date=2026-10-09')
})

test('the date is kept, changed or removed on purpose', () => {
  assert.equal(withLog('?log&date=2026-10-09', 'hand'), '?log=hand&date=2026-10-09')
  assert.equal(withLog('?log&date=2026-10-09', 'start', null), '?log')
  assert.equal(logDate('?log&date=2026-10-09'), '2026-10-09')
  assert.equal(logDate('?log'), null)
})

test('closing removes the flag and the date, and nothing else', () => {
  assert.equal(withoutLog('?log=hand&date=2026-10-09'), '')
  assert.equal(withoutLog('?tab=2&log'), '?tab=2')
})

test('only a positive number counts as pushed history', () => {
  assert.equal(logDepth(null), 0)
  assert.equal(logDepth({}), 0)
  assert.equal(logDepth({ logDepth: 2 }), 2)
  assert.equal(logDepth({ logDepth: '2' }), 0)
  assert.equal(logDepth({ logDepth: -1 }), 0)
})
