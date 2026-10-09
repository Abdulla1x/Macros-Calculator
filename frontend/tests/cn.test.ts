// Run with `npm test` (see photoSize.test.ts for how).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { cn } from '../src/lib/utils.ts'

test('a type style and a text colour both survive', () => {
  assert.equal(cn('text-ink text-field-label'), 'text-ink text-field-label')
  assert.equal(cn('text-field-label text-ink-2'), 'text-field-label text-ink-2')
  assert.equal(cn('text-display-number text-band-ink'), 'text-display-number text-band-ink')
})

test('two type styles, two colours or two radii resolve to the later one', () => {
  assert.equal(cn('text-title text-small'), 'text-small')
  assert.equal(cn('text-sm text-field-label'), 'text-field-label')
  assert.equal(cn('text-ink text-action'), 'text-action')
  assert.equal(cn('bg-ground bg-band'), 'bg-band')
  assert.equal(cn('rounded-control rounded-log'), 'rounded-log')
})

test('every text-* utility index.css defines is known to cn as a font size', () => {
  const css = readFileSync(new URL('../../src/index.css', import.meta.url), 'utf8')
  const styles = [...css.matchAll(/@utility (text-[\w-]+)/g)].map((m) => m[1]!)
  assert.ok(styles.length >= 7, 'index.css type styles not found')
  for (const style of styles) {
    assert.equal(cn(`text-ink ${style}`), `text-ink ${style}`, `${style} is treated as a colour`)
  }
})
