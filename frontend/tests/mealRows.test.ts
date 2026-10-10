// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { emptyRow, mealTotals, rowFromAnalyzedItem, rowTotals } from '../src/lib/mealRows.ts'
import type { AnalyzedItem, Food } from '../src/types.ts'

const item = (over: Partial<AnalyzedItem> = {}): AnalyzedItem => ({
  name: 'Rice, cooked',
  portion_grams: 200,
  calories: 260,
  protein: 5,
  carbs: 56,
  fat: null,
  confidence: 'medium',
  matched_food_name: null,
  ...over,
})

const oats = { id: 1, name: 'Oats', serving_size: 100, calories: 380, protein: 13, carbs: 60, fat: 7 } as Food

test('an estimated item passes the model’s numbers through unchanged', () => {
  const row = rowFromAnalyzedItem(item(), [])
  assert.deepEqual(rowTotals(row), { calories: 260, protein: 5, carbs: 56, fat: null })
  assert.equal(row.fromLibrary, false)
})

test('an item matched to a saved food takes the food’s macros at the model’s portion', () => {
  const row = rowFromAnalyzedItem(item({ name: 'Porridge oats', portion_grams: 50, matched_food_name: 'Oats' }), [oats])
  assert.equal(row.fromLibrary, true)
  assert.equal(row.name, 'Oats')
  assert.deepEqual(rowTotals(row), { calories: 190, protein: 6.5, carbs: 30, fat: 3.5 })
})

test('totals skip invalid rows and leave an untracked macro null, not zero', () => {
  const rice = rowFromAnalyzedItem(item(), [])
  const blank = emptyRow()
  const totals = mealTotals([rice, blank, rowFromAnalyzedItem(item({ carbs: null }), [])])
  assert.equal(totals.calories, 520)
  assert.equal(totals.carbs, 56)
  assert.equal(totals.fat, null)
})
