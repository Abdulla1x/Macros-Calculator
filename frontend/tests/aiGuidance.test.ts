// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { noteWithExtras, shouldAskAboutHidden } from '../src/lib/aiGuidance.ts'

test('asks only when photos are the whole story', () => {
  assert.equal(shouldAskAboutHidden(2, ''), true)
  assert.equal(shouldAskAboutHidden(1, '   '), true)
  assert.equal(shouldAskAboutHidden(0, ''), false)
  assert.equal(shouldAskAboutHidden(2, 'salmon'), false)
})

test('picked extras become one plain line the model reads', () => {
  assert.equal(noteWithExtras('', []), '')
  assert.equal(noteWithExtras('', ['Oil']), 'Also in it: oil.')
  assert.equal(noteWithExtras('', ['Oil', 'Sauce']), 'Also in it: oil and sauce.')
  assert.equal(noteWithExtras('', ['Oil', 'Butter', 'Nut butter']), 'Also in it: oil, butter and nut butter.')
  assert.equal(noteWithExtras(' rice bowl ', ['Sugar or honey']), 'rice bowl\nAlso in it: sugar or honey.')
})
