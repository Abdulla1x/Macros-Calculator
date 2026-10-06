// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DATA_CREDITS, SOURCE_BADGE, SOURCE_NAME, sourceAfterEdit } from '../src/lib/foodSources.ts'

test('changing any number makes a picked row the user’s own', () => {
  for (const field of ['servingSize', 'calories', 'protein', 'carbs', 'fat']) {
    assert.equal(sourceAfterEdit('usda', [field]), 'user', field)
  }
})

test('a rename or a weight keeps the pick’s source, as the server’s PUT does', () => {
  assert.equal(sourceAfterEdit('ciqual', ['name']), 'ciqual')
  assert.equal(sourceAfterEdit('ciqual', ['weight']), 'ciqual')
  assert.equal(sourceAfterEdit('openfoodfacts', ['saveToLibrary']), 'openfoodfacts')
})

test('a row that is already the user’s stays so', () => {
  assert.equal(sourceAfterEdit('user', ['name']), 'user')
  assert.equal(sourceAfterEdit('user', ['calories']), 'user')
})

test('every source the server accepts has a badge and a name', () => {
  const sources = ['user', 'openfoodfacts', 'usda', 'cofid', 'ciqual', 'afcd', 'cnf'] as const
  for (const source of sources) {
    assert.ok(SOURCE_BADGE[source], source)
    assert.ok(SOURCE_NAME[source], source)
  }
})

test('every third-party source is credited exactly once', () => {
  const credited = DATA_CREDITS.map((credit) => credit.source).sort()
  assert.deepEqual(credited, ['afcd', 'ciqual', 'cnf', 'cofid', 'openfoodfacts', 'usda'])
})
