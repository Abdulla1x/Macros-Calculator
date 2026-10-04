// Run with `npm test`: tsconfig.test.json compiles this with the project's own
// tsc, then Node's built-in runner executes it. No test framework, no new
// dependency -- and the code under test must stay free of the DOM to run here.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fitWithin, jpegName, preferEncoded } from '../src/lib/photoSize.ts'

test('a landscape photo is scaled so its width is the limit', () => {
  assert.deepEqual(fitWithin(4000, 3000, 1024), { width: 1024, height: 768 })
})

test('a portrait photo is scaled so its height is the limit', () => {
  assert.deepEqual(fitWithin(3000, 4000, 1024), { width: 768, height: 1024 })
})

test('a square photo keeps both sides equal', () => {
  assert.deepEqual(fitWithin(3000, 3000, 1536), { width: 1536, height: 1536 })
})

test('a photo exactly at the limit is left alone', () => {
  assert.deepEqual(fitWithin(1024, 683, 1024), { width: 1024, height: 683 })
})

test('a photo smaller than the limit is never upscaled', () => {
  assert.deepEqual(fitWithin(600, 400, 1024), { width: 600, height: 400 })
  assert.deepEqual(fitWithin(1, 1, 1024), { width: 1, height: 1 })
})

test('an extreme strip never rounds a side down to zero', () => {
  assert.deepEqual(fitWithin(8000, 2, 1024), { width: 1024, height: 1 })
})

test('the re-encode is used only when it is actually smaller', () => {
  assert.equal(preferEncoded(4_000_000, 200_000), true)
  assert.equal(preferEncoded(80_000, 95_000), false)
  assert.equal(preferEncoded(80_000, 80_000), false)
  // An empty blob is a failed encode, not a very good one.
  assert.equal(preferEncoded(80_000, 0), false)
})

test('the filename follows the bytes', () => {
  assert.equal(jpegName('IMG_1234.HEIC'), 'IMG_1234.jpg')
  assert.equal(jpegName('meal.photo.png'), 'meal.photo.jpg')
  assert.equal(jpegName('no-extension'), 'no-extension.jpg')
  assert.equal(jpegName('.hidden'), '.hidden.jpg')
  assert.equal(jpegName(''), 'photo.jpg')
})
