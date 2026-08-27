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
// ---------------------------------------------------------------------------
// Setup (once per machine)
//
//   1. From the repo root:  npm install --no-save playwright-core
//      It is intentionally absent from frontend/package.json -- it is a local
//      verification tool, not something the app ships, and CI has no reason to
//      download a browser to run `npm ci`.
//   2. npx playwright-core install chromium-headless-shell
//   3. On Linux without root, the shell will be missing system libraries.
//      Extract them locally instead of installing:
//        apt-get download libnspr4 libnss3 libasound2t64
//        for f in *.deb; do dpkg -x "$f" libs; done
//        export LD_LIBRARY_PATH="$PWD/libs/usr/lib/x86_64-linux-gnu"
//      Point LD_LIBRARY_PATH at the directory holding the .so files, not at the
//      extraction root. Confirm before running:
//        LD_LIBRARY_PATH=... ldd <headless-shell> | grep "not found"
//      That must print nothing.
//
// Both servers must already be running (scripts/dev.sh, or the backend and
// frontend started by hand).
//
// ⚠ Start the backend with ADMIN_EMAILS set to the snapshot account's address,
// or /admin renders "Not found." instead of its two charts -- two of the five
// charts in the app, silently missing from the comparison.
//
// ---------------------------------------------------------------------------
// Environment
//
//   BASE_URL      frontend origin      (default http://localhost:5173)
//   API_URL       backend origin       (default http://localhost:8000)
//   EMAIL         snapshot account     (default snapshot@example.com)
//   PASSWORD      snapshot password    (default snapshot-password-1)
//   CHROME_PATH   headless shell       (default: newest chromium_headless_shell
//                                       under ~/.cache/ms-playwright)
//   SEED_DAYS     days of data to seed (default 14)
//
// ---------------------------------------------------------------------------
// Why each determinism measure below exists -- every one of them is a real
// source of drift that would otherwise show up as a false diff:
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
// case the harness exists for. Repeat both checks after changing anything here:
// a harness that reports spurious differences gets ignored, which is worse than
// not having one at all.

import { mkdir, writeFile } from 'node:fs/promises'
import { readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'
const API_URL = process.env.API_URL ?? 'http://localhost:8000'
const EMAIL = process.env.EMAIL ?? 'snapshot@example.com'
const PASSWORD = process.env.PASSWORD ?? 'snapshot-password-1'
const SEED_DAYS = Number(process.env.SEED_DAYS ?? 14)

const outDir = process.argv[2]
if (!outDir) {
  console.error('usage: node scripts/dom-snapshot.mjs <output-dir>')
  process.exit(2)
}

// Routes that render without a token. Kept in a separate context from the rest:
// nothing redirects an authenticated visitor away from /login, but snapshotting
// them signed out is what a signed-out visitor actually sees.
const PUBLIC_ROUTES = ['/login', '/signup', '/forgot-password', '/reset-password']

// Everything behind RequireAuth. `/nope` is any unmatched address, which renders
// NotFound inside the Layout. There are no parameterised routes in this app, so
// this list is the whole surface.
//
// `/settings` is kept alongside its five panels on purpose: it is a redirect to
// /settings/goals, and snapshotting it is what would catch the redirect quietly
// breaking or landing somewhere else.
const PRIVATE_ROUTES = [
  '/',
  '/log',
  '/weight',
  '/analytics',
  '/settings',
  '/settings/goals',
  '/settings/body',
  '/settings/trackers',
  '/settings/food',
  '/settings/account',
  '/whats-new',
  '/admin',
  '/nope',
]

/** playwright-core resolves from the repo-root node_modules; fall back to a
 *  path relative to this file for callers running from elsewhere. */
async function loadChromium() {
  try {
    return (await import('playwright-core')).chromium
  } catch {
    const url = new URL('../node_modules/playwright-core/index.mjs', import.meta.url)
    return (await import(url.href)).chromium
  }
}

/** The headless shell, without hard-coding a build revision -- the number in
 *  the directory name moves with every playwright upgrade. */
function findExecutable() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH
  const root = join(homedir(), '.cache', 'ms-playwright')
  const builds = readdirSync(root)
    .filter((name) => name.startsWith('chromium_headless_shell-'))
    .sort()
  const newest = builds[builds.length - 1]
  if (!newest) {
    throw new Error(
      `no chromium_headless_shell-* under ${root}; run: npx playwright-core install chromium-headless-shell`,
    )
  }
  return join(root, newest, 'chrome-headless-shell-linux64', 'chrome-headless-shell')
}

async function apiJson(path, init) {
  const response = await fetch(`${API_URL}${path}`, init)
  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    /* Non-JSON error pages are reported by status alone. */
  }
  return { status: response.status, body }
}

/** Sign up, or log in if the fixed account already exists. Re-running against
 *  the same database is the common case: the point is a stable account, not a
 *  fresh one. */
async function authenticate() {
  const headers = { 'Content-Type': 'application/json' }
  const credentials = JSON.stringify({ email: EMAIL, password: PASSWORD })

  const signup = await apiJson('/api/auth/signup', { method: 'POST', headers, body: credentials })
  if (signup.status === 201) return { token: signup.body.access_token, fresh: true }

  const login = await apiJson('/api/auth/login', { method: 'POST', headers, body: credentials })
  if (login.status === 200) return { token: login.body.access_token, fresh: false }

  throw new Error(
    `could not authenticate ${EMAIL}: signup ${signup.status}, login ${login.status}`,
  )
}

const isoDaysAgo = (days) => new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)

/** Meals and weigh-ins for the last SEED_DAYS days, so every chart has
 *  something to draw. Values are a deterministic ramp, not random. */
async function seed(token) {
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  for (let day = 0; day < SEED_DAYS; day += 1) {
    const date = isoDaysAgo(day)
    await apiJson('/api/meals', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        date,
        name: `Snapshot meal ${day}`,
        calories: 1600 + day * 40,
        protein: 110 + day,
        carbs: 150 + day,
        fat: 55 + day,
      }),
    })
    await apiJson('/api/weights', {
      method: 'POST',
      headers,
      body: JSON.stringify({ date, weight_kg: 82.5 - day * 0.05 }),
    })
  }
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
 *  Vite's dev server appends `?t=<epoch-ms>` to the module script tag after any
 *  file it serves changes, so every snapshot taken after an edit differs from
 *  every snapshot taken before one -- in all twelve files, for a reason that has
 *  nothing to do with the app. */
function normalise(html) {
  const seen = new Map()
  return html
    .replace(/_r_[0-9a-z]+_/g, (match) => {
      if (!seen.has(match)) seen.set(match, `_r_${seen.size}_`)
      return seen.get(match)
    })
    .replace(/(\.tsx)\?t=\d+/g, '$1')
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

async function capture(context, routes, label) {
  const page = await context.newPage()
  for (const route of routes) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'domcontentloaded' })
    // The SPA commits the new route after navigation resolves, so waiting on
    // the URL alone reads the previous page. A heading is route-specific
    // content; networkidle then covers the data each page fetches for itself.
    await page.waitForSelector('h1, h2', { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    await writeFile(join(outDir, fileNameFor(route)), await stableSnapshot(page), 'utf8')
    console.log(`  ${label} ${route}`)
  }
  await page.close()
}

const chromium = await loadChromium()
await mkdir(outDir, { recursive: true })

const { token, fresh } = await authenticate()
console.log(`account ${EMAIL} (${fresh ? 'created' : 'existing'})`)
if (fresh) {
  await seed(token)
  console.log(`seeded ${SEED_DAYS} days of meals and weigh-ins`)
}

const announcements = await apiJson('/api/announcements')
const seenIds = (announcements.body?.items ?? []).map((item) => item.id)

const browser = await chromium.launch({ executablePath: findExecutable() })
try {
  const viewport = { width: 1280, height: 900 }

  const anonymous = await browser.newContext({ viewport })
  await capture(anonymous, PUBLIC_ROUTES, 'public ')
  await anonymous.close()

  const authed = await browser.newContext({ viewport })
  // Before any page script runs: the token is read once at module load, and the
  // announcements modal decides what to show on its first render.
  await authed.addInitScript(
    ([sessionToken, ids]) => {
      localStorage.setItem('macros_token', sessionToken)
      localStorage.setItem('macros_seen_announcements', JSON.stringify(ids))
    },
    [token, seenIds],
  )
  await capture(authed, PRIVATE_ROUTES, 'authed ')
  await authed.close()
} finally {
  await browser.close()
}

console.log(`\nwrote ${PUBLIC_ROUTES.length + PRIVATE_ROUTES.length} snapshots to ${outDir}`)
