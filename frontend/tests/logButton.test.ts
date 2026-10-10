// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { logButtonLabel, logButtonState } from '../src/components/shell/logButton.ts'

test('a running estimate outranks an unseen one', () => {
  assert.equal(logButtonState(true, true), 'working')
  assert.equal(logButtonState(true, false), 'working')
  assert.equal(logButtonState(false, true), 'ready')
  assert.equal(logButtonState(false, false), 'idle')
})

test('the tab bar keeps a short label; the spoken name always carries the state', () => {
  for (const state of ['idle', 'working', 'ready'] as const) {
    assert.ok(logButtonLabel('bar', state).visible.length <= 5, state)
    assert.equal(logButtonLabel('bar', state).spoken, logButtonLabel('rail', state).spoken)
  }
  // Label in name (WCAG 2.5.3): what is spoken contains what is shown.
  for (const place of ['bar', 'rail'] as const) {
    for (const state of ['idle', 'working', 'ready'] as const) {
      const { visible, spoken } = logButtonLabel(place, state)
      assert.ok(spoken.toLowerCase().includes(visible.replace('…', '').toLowerCase()), `${place} ${state}`)
    }
  }
})
