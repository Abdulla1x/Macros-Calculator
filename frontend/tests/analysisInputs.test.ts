// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sameInputs } from '../src/lib/analysisInputs.ts'

// Stand-ins for File objects: only their identity matters to the rule.
const photo1 = { name: 'a.jpg' }
const photo2 = { name: 'b.jpg' }
const base = { note: '200g chicken, 150g rice', photos: [photo1, photo2], foodIds: [3, 7] }

test('the same note, photos and foods are the same inputs', () => {
  assert.equal(sameInputs(base, { ...base, photos: [photo1, photo2], foodIds: [3, 7] }), true)
})

test('surrounding whitespace in the note is not a change, because the request trims it', () => {
  assert.equal(sameInputs(base, { ...base, note: '  200g chicken, 150g rice\n' }), true)
})

test('any edit to the note is a change', () => {
  assert.equal(sameInputs(base, { ...base, note: '200g chicken, 100g rice' }), false)
})

test('a photo added, removed or reordered is a change', () => {
  assert.equal(sameInputs(base, { ...base, photos: [photo1, photo2, { name: 'c.jpg' }] }), false)
  assert.equal(sameInputs(base, { ...base, photos: [photo1] }), false)
  assert.equal(sameInputs(base, { ...base, photos: [photo2, photo1] }), false)
})

test('the same picture picked again is a new upload, so it is a change', () => {
  assert.equal(sameInputs(base, { ...base, photos: [photo1, { name: 'b.jpg' }] }), false)
})

test('attaching or removing a saved food is a change', () => {
  assert.equal(sameInputs(base, { ...base, foodIds: [3, 7, 9] }), false)
  assert.equal(sameInputs(base, { ...base, foodIds: [3] }), false)
})

test('the order foods were attached in is not a change', () => {
  assert.equal(sameInputs(base, { ...base, foodIds: [7, 3] }), true)
})

test('a text-only estimate re-run with the same text is the same inputs', () => {
  const textOnly = { note: 'one banana', photos: [], foodIds: [] }
  assert.equal(sameInputs(textOnly, { note: 'one banana', photos: [], foodIds: [] }), true)
})
