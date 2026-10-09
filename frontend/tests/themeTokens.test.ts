// Run with `npm test` (see photoSize.test.ts for how).
//
// theme.css is generated from DESIGN.md's token block, and DESIGN.md promises
// every text pair is at least 4.5:1 and every non-text pair at least 3:1, in
// all eight palettes, light and dark, and in the Label style. These tests hold
// both promises: a hand edit to either file that drifts from the other, or a
// colour that breaks contrast in any one of the 18 themes, fails here.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// Compiled to dist-tests/tests/, so the sources are two and three levels up.
const css = readFileSync(new URL('../../src/theme.css', import.meta.url), 'utf8')
const design = readFileSync(new URL('../../../DESIGN.md', import.meta.url), 'utf8')

type Tokens = Record<string, string>

const tokensIn = (body: string): Tokens =>
  Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]))

/** theme.css's blocks, by selector. */
const blocks: Record<string, Tokens> = Object.fromEntries(
  [...css.matchAll(/\n(:root[^{]*)\{([^}]*)\}/g)].map((m) => [m[1]!.trim(), tokensIn(m[2]!)]),
)

/** DESIGN.md's token block, by its comment heading. */
const designBlock = (() => {
  const start = design.indexOf('```css\n/* Daylight (default) */')
  assert.ok(start >= 0, "DESIGN.md's token block was not found")
  const body = design.slice(start + '```css\n'.length, design.indexOf('```', start + 10))
  return Object.fromEntries(
    [...body.matchAll(/\/\* (.+?) \*\/\n([\s\S]*?)(?=\n\/\*|$)/g)].map((m) => [m[1]!, tokensIn(m[2]!)]),
  )
})()

const PALETTES = ['daylight', 'ocean', 'sand', 'berry', 'mono', 'ember', 'citrus', 'violet'] as const

const selectorFor = (palette: string, dark: boolean): string =>
  palette === 'daylight'
    ? dark ? ':root[data-theme="dark"]' : ':root'
    : `:root[data-palette="${palette}"]${dark ? '[data-theme="dark"]' : ''}`

const block = (selector: string): Tokens => {
  const found = blocks[selector]
  assert.ok(found, `theme.css has no block for ${selector}`)
  return found
}

/** The tokens one theme ends up with, applied in the order the CSS cascade
 *  applies them (the header of theme.css explains the order). */
function compose(palette: string, dark: boolean, label: boolean): Tokens {
  const tokens: Tokens = { ...block(':root') }
  if (dark) Object.assign(tokens, block(':root[data-theme="dark"]'))
  if (palette !== 'daylight') {
    Object.assign(tokens, block(selectorFor(palette, false)))
    if (dark) Object.assign(tokens, block(selectorFor(palette, true)))
  }
  if (label) {
    Object.assign(tokens, block(':root[data-style="label"]'))
    if (dark) Object.assign(tokens, block(':root[data-style="label"][data-theme="dark"]'))
  }
  const resolve = (value: string, depth = 0): string => {
    const ref = /^var\(--([\w-]+)\)$/.exec(value)
    if (!ref) return value
    assert.ok(depth < 5, `var() cycle at ${value}`)
    const target = tokens[ref[1]!]
    assert.ok(target, `--${ref[1]} is used but never defined`)
    return resolve(target, depth + 1)
  }
  return Object.fromEntries(Object.entries(tokens).map(([key, value]) => [key, resolve(value)]))
}

/** WCAG 2.x contrast ratio of two #rrggbb colours. */
function contrast(a: string, b: string): number {
  const luminance = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    }) as [number, number, number]
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

test('theme.css matches DESIGN.md token for token', () => {
  for (const [name, tokens] of Object.entries(designBlock)) {
    const palette = name.split(' ')[0]!.toLowerCase()
    const dark = name.endsWith('dark')
    const selector =
      palette === 'label'
        ? `:root[data-style="label"]${dark ? '[data-theme="dark"]' : ''}`
        : selectorFor(palette, dark)
    for (const [key, value] of Object.entries(tokens)) {
      assert.equal(block(selector)[key], value, `${name}: --${key}`)
    }
  }
})

test('every palette light block sets the full token set, so nothing leaks between palettes', () => {
  const full = Object.keys(block(':root')).sort()
  for (const palette of PALETTES.slice(1)) {
    assert.deepEqual(Object.keys(block(selectorFor(palette, false))).sort(), full, palette)
  }
  assert.deepEqual(Object.keys(block(':root[data-style="label"]')).sort(), full, 'label')
})

// [foreground, background, minimum]. Text at 4.5:1; the target tick and the
// gauge segments are non-text, at 3:1. The action colour is text too (links).
const PAIRS: [string, string, number][] = [
  ['ink', 'ground', 4.5],
  ['ink-2', 'ground', 4.5],
  ['ink', 'field', 4.5],
  ['ink-2', 'field', 4.5],
  ['ink', 'label', 4.5],
  ['action', 'ground', 4.5],
  ['action-ink', 'action', 4.5],
  ['fact', 'ground', 4.5],
  ['band-ink', 'band', 4.5],
  ['band-ink-2', 'band', 4.5],
  ['plan', 'ground', 3],
  ['band-plan', 'band', 3],
  ['fill', 'track', 3],
  ['band-fill', 'band-track', 3],
]

test('every pair passes WCAG contrast in all 18 themes', () => {
  const themes = [
    ...PALETTES.flatMap((palette) => [false, true].map((dark) => ({ palette, dark, label: false }))),
    { palette: 'daylight', dark: false, label: true },
    { palette: 'daylight', dark: true, label: true },
  ]
  assert.equal(themes.length, 18)
  for (const { palette, dark, label } of themes) {
    const tokens = compose(palette, dark, label)
    const name = `${label ? 'label' : palette} ${dark ? 'dark' : 'light'}`
    for (const [fg, bg, minimum] of PAIRS) {
      const ratio = contrast(tokens[fg]!, tokens[bg]!)
      assert.ok(ratio >= minimum, `${name}: --${fg} on --${bg} is ${ratio.toFixed(2)}:1, needs ${minimum}:1`)
    }
  }
})

test('the Label style ignores the palette underneath it', () => {
  for (const dark of [false, true]) {
    const base = compose('daylight', dark, true)
    for (const palette of PALETTES) {
      assert.deepEqual(compose(palette, dark, true), base, `label over ${palette} ${dark ? 'dark' : 'light'}`)
    }
  }
})
