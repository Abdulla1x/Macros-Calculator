// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SECTION_HOME, sectionFor } from '../src/components/shell/sections.ts'

test('each tab owns its pages', () => {
  assert.equal(sectionFor('/'), 'today')
  for (const path of ['/analytics', '/weight', '/review']) assert.equal(sectionFor(path), 'progress', path)
  assert.equal(sectionFor('/log'), 'log')
  for (const path of ['/settings', '/settings/goals', '/settings/account', '/whats-new']) {
    assert.equal(sectionFor(path), 'you', path)
  }
})

test('pages outside the four tabs light none of them', () => {
  for (const path of ['/admin', '/nope', '/settingsx', '/weights', '/logbook']) {
    assert.equal(sectionFor(path), null, path)
  }
})

test('every tab’s home is a page of that tab', () => {
  for (const [section, home] of Object.entries(SECTION_HOME)) assert.equal(sectionFor(home), section)
})
