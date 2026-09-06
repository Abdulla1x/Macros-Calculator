#!/usr/bin/env node
//
// Snapshot the rendered DOM of every route, with all `class` attributes
// stripped, so a refactor can be proved not to have changed anything.
//
// The refactoring phases of this project have one invariant: *same DOM,
// different classes*. Moving a component into its own file must not alter a
// single rendered element; replacing a hand-written class string with a shared
// one must not either. There are no frontend tests here, so without this the
// only evidence a refactor was inert is "it looked fine", and the box this
// codebase has been burned by before is precisely the change that looks fine.
//
// Stripping `class` is what makes the comparison useful rather than trivially
// noisy: it lets a styling change pass while still failing on a stray wrapper
// <div>, a dropped attribute, a reordered sibling, or a section that quietly
// stopped rendering. `style` is deliberately NOT stripped -- recharts writes
// measured pixel sizes there, so a chart that collapses shows up as a diff.
//
// Usage:
//
//   node scripts/dom-snapshot.mjs <output-dir>
//
// Run it once on the base branch and once on the working branch, then diff:
//
//   git switch main
//   node scripts/dom-snapshot.mjs /tmp/snap-before
//   git switch my-branch
//   node scripts/dom-snapshot.mjs /tmp/snap-after
//   diff -ru /tmp/snap-before /tmp/snap-after
//
// Deliberately NOT part of scripts/check.sh. That gate is five fast, offline
// commands; this one needs a browser, a running backend and a running frontend,
// and belongs in the same manual pass as the rest of the browser checks.
//
// ⚠ Setup, the route lists, the seeded account and the navigation loop live in
// scripts/lib/harness.mjs, which scripts/a11y-audit.mjs shares. Read its header
// before the first run on a machine -- in particular, playwright-core and
// axe-core must be installed in ONE npm command or the second install deletes
// the first.
//
// ---------------------------------------------------------------------------
// Why each determinism measure exists -- every one of them is a real source of
// drift that would otherwise show up as a false diff. The first five are now
// enforced in the shared harness and are listed here because THIS is the script
// whose output they keep honest; the last two are below, in this file.
//
//   * A FIXED account email. It renders in the sidebar and in Settings ->
//     Account, so a timestamped signup changes the DOM on every run.
//   * SEEDED data. Without it every chart page renders an empty state, and the
//     chart styling would be entirely uncovered by the comparison.
//   * PRE-SEEDED `macros_seen_announcements`. A brand-new account gets a
//     zero-note welcome modal, but it is still a full-screen overlay, and its
//     counts change whenever a release note is added.
//   * A FIXED viewport, because measured chart sizes are written to `style`.
//   * networkidle before reading, so async content has landed.
//   * POLLING until two reads agree, because recharts tweens its lines in over
//     1.5s and a single read catches a different animation frame every time.
//   * RENUMBERED React useId values, whose counter depends on mount order, and
//     a STRIPPED Vite `?t=<epoch>` cache-buster, which changes after any edit.
//
// The last three were not predicted. Two were found by running the script twice
// against unchanged code and diffing its output against itself; the third only
// appeared once a file had actually been edited between two runs, which is the
// case the harness exists for. Repeat both checks after changing anything here
// OR in the shared harness: a harness that reports spurious differences gets
// ignored, which is worse than not having one at all.

import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

import {
  PRIVATE_ROUTES,
  PUBLIC_ROUTES,
  openSession,
  visitRoutes,
} from './lib/harness.mjs'

const outDir = process.argv[2]
if (!outDir) {
  console.error('usage: node scripts/dom-snapshot.mjs <output-dir>')
  process.exit(2)
}

/** Replace the values that change between runs without the page changing.
 *
 *  React's useId produces ids like `_r_4_`, numbered by how many components
 *  mounted before the one being numbered -- which varies with the order async
 *  data happens to land. The values are meaningless, but they appear in `id`
 *  and in `clip-path="url(#...)"`, so left alone they diff on every run.
 *  Renumbering them in document order is stable between runs while still
 *  showing up if the count of them genuinely changes.
 *
 *  recharts has a counter of its own, and the same problem. Its clip paths are
 *  named `recharts<n>-clip` from a module-level counter that advances on every
 *  chart instance EVER mounted in the tab, so it depends on how many times a
 *  chart mounted on the pages visited earlier -- which varies with when each
 *  page's fetch resolved. Measured: two runs of identical code, minutes apart,
 *  gave `recharts5-clip` and `recharts13-clip` on /analytics. That was a false
 *  diff on this file in EVERY comparison the harness has ever been used for,
 *  and a harness that always reports one change nobody made is a harness whose
 *  output stops being read.
 *
 *  Vite's dev server appends `?t=<epoch-ms>` to the module script tag after any
 *  file it serves changes, so every snapshot taken after an edit differs from
 *  every snapshot taken before one -- in all twelve files, for a reason that has
 *  nothing to do with the app.
 *
 *  /admin's keep-warm card reports live server state -- uptime, boot time, how
 *  many health checks have arrived, what time it is in the window's zone. Every
 *  one of those changes between two runs of identical code, which would make
 *  admin.html differ forever. The elements carry `data-live`, so their text is
 *  blanked here while the elements themselves, and the count of them, are still
 *  compared: a fact that stops rendering still shows up as a diff. Marking them
 *  at the source rather than pattern-matching the values is deliberate -- a
 *  regex for "things that look like a duration" would eventually blank a real
 *  change. */
function normalise(html) {
  // One counter per id scheme, each numbering in document order. Separate maps
  // so a change in how many of one kind exist cannot renumber the other.
  const renumber = (format) => {
    const seen = new Map()
    return (match) => {
      if (!seen.has(match)) seen.set(match, format(seen.size))
      return seen.get(match)
    }
  }
  return html
    .replace(/_r_[0-9a-z]+_/g, renumber((n) => `_r_${n}_`))
    // Matches both the `id` and the `clip-path="url(#...)"` that references it,
    // which is why this renumbers the prefix rather than the whole id.
    .replace(/recharts\d+/g, renumber((n) => `recharts${n}`))
    .replace(/(\.tsx)\?t=\d+/g, '$1')
    // Text inside a data-live element, which is server state that moves on its
    // own. Bounded by a negated class rather than a lazy quantifier, so it stops
    // dead at the first `<` and can only ever eat one element's own text node;
    // these are leaves by construction.
    .replace(/(<[^>]*\sdata-live="[^"]*"[^>]*>)[^<]*/g, '$1LIVE')
}

/** Read the body with every `class` attribute removed, one tag per line so the
 *  result diffs readably instead of as a single enormous line. */
async function snapshot(page) {
  const html = await page.evaluate(() => {
    const clone = document.body.cloneNode(true)
    clone.removeAttribute('class')
    for (const element of clone.querySelectorAll('*')) element.removeAttribute('class')
    return clone.innerHTML
  })
  return `${normalise(html).replaceAll('><', '>\n<')}\n`
}

/** Read repeatedly until two consecutive reads agree.
 *
 *  recharts animates its lines and areas in by tweening stroke-dasharray over
 *  1.5s, so a snapshot taken the moment the network goes idle catches the
 *  animation mid-flight and lands on a different frame every run. Dashboard and
 *  Analytics animate; Weight and Admin already pass isAnimationActive={false}.
 *  Polling for stability rather than sleeping a fixed 2s also keeps the routes
 *  with no animation fast. */
async function stableSnapshot(page, attempts = 30, intervalMs = 300) {
  let previous = null
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const current = await snapshot(page)
    if (current === previous) return current
    previous = current
    await page.waitForTimeout(intervalMs)
  }
  throw new Error(`DOM never settled after ${attempts} reads; something is animating forever`)
}

const fileNameFor = (route) => `${route === '/' ? 'index' : route.slice(1).replaceAll('/', '_')}.html`

const capture = (context, routes, label) =>
  visitRoutes(context, routes, async (page, route) => {
    await writeFile(join(outDir, fileNameFor(route)), await stableSnapshot(page), 'utf8')
    console.log(`  ${label} ${route}`)
  })

await mkdir(outDir, { recursive: true })

const session = await openSession()
try {
  const viewport = { width: 1280, height: 900 }

  const anonymous = await session.anonymousContext(viewport)
  await capture(anonymous, PUBLIC_ROUTES, 'public ')
  await anonymous.close()

  const authed = await session.authedContext(viewport)
  await capture(authed, PRIVATE_ROUTES, 'authed ')
  await authed.close()
} finally {
  await session.browser.close()
}

console.log(`\nwrote ${PUBLIC_ROUTES.length + PRIVATE_ROUTES.length} snapshots to ${outDir}`)
