#!/usr/bin/env node
//
// Retake every screenshot in the README, at both widths, from the running app.
//
// The README's screenshots went stale three times before this script existed:
// a phase moves a screen, nobody retakes the images, and the front door shows
// a layout the app has not had for months. Taking them by hand is why -- eight
// screens at two widths is sixteen captures, each needing an account with
// enough data in it that no screen renders an empty state. So this seeds the
// data, drives the app, and writes all sixteen files.
//
// Usage:
//
//   node scripts/screenshots.mjs screenshots
//
// Both servers must already be running (scripts/dev.sh).
//
// ⚠ It signs up, DELETES and re-creates the demo account every run. Seeding is
// additive, so re-running against a surviving account gives every day two of
// every meal -- which doubles mean intake and, with it, the measured burn and
// every target derived from it. Point BASE_URL/API_URL at a local server only.
//
// ---------------------------------------------------------------------------
// Setup (once per machine)
//
// Identical to scripts/dom-snapshot.mjs -- see that file's header for the full
// recipe, including the no-root path for the system libraries chromium needs
// on Linux. In short: `npm install --no-save playwright-core` from the repo
// root, then `npx playwright-core install chromium-headless-shell`.
//
// Two things that are only this script's problem:
//
//   * AN EMOJI FONT. The tab bar, the tracker cards and the nav are emoji. A
//     machine with no colour emoji font renders every one as a tofu box, and
//     the screenshots are unusable while looking merely odd. Install one
//     (fonts-noto-color-emoji) and confirm with `fc-list | grep -i emoji`.
//   * PNGQUANT, optional. If it is on PATH the captures are quantised in
//     place, which takes the set from ~3.7 MB to ~1.2 MB with no visible
//     difference. Without it the images are simply larger.
//
// ---------------------------------------------------------------------------
// Environment
//
//   BASE_URL      frontend origin   (default http://localhost:5173)
//   API_URL       backend origin    (default http://localhost:8000)
//   EMAIL         demo account      (default demo@example.com)
//   PASSWORD      demo password     (default demo-password-1)
//   CHROME_PATH   headless shell    (default: newest chromium_headless_shell
//                                    under ~/.cache/ms-playwright)
//   SEED_DAYS     days of data      (default 30)
//
// The AI panel needs an analysis on screen, and analyses cost a provider call.
// The script asks GET /api/ai/status which of the two situations it is in:
//
//   * Backend configured with a GEMINI_API_KEY -> a real analysis, from the
//     real model. This is how the committed images were taken.
//   * No key -> the analyze response is intercepted and a representative one
//     served instead, so the panel still renders and the other fifteen
//     captures are not held hostage to a key. It says so on stdout.
//
// ---------------------------------------------------------------------------
// Why the seed data looks the way it does. Every figure on these screens is
// derived from the logs, so seed values that do not hang together produce
// screenshots that quietly contradict themselves -- a "measured burn" that
// disagrees with the intake above it, a weekly review reporting a gain on an
// account whose goal is a loss. The numbers below are chosen so the whole set
// is coherent: ~2,340 kcal/day against a trend falling 0.35 kg/week, which is
// the goal rate the profile asks for, and which lands the measured TDEE and
// the auto-calculated target within a few kcal of the intake.

import { mkdir } from 'node:fs/promises'
import { readdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'
const API_URL = process.env.API_URL ?? 'http://localhost:8000'
const EMAIL = process.env.EMAIL ?? 'demo@example.com'
const PASSWORD = process.env.PASSWORD ?? 'demo-password-1'
const SEED_DAYS = Number(process.env.SEED_DAYS ?? 30)

const outDir = process.argv[2]
if (!outDir) {
  console.error('usage: node scripts/screenshots.mjs <output-dir>')
  process.exit(2)
}

const DESKTOP = { width: 1280, height: 832 }
const MOBILE = { width: 390, height: 844 }

// The AI panel is a description box, a photo/voice row, the analyze controls
// and the estimate card stacked -- about 1,100px on desktop. At the standard
// height the shot has to choose between the input and the result, so the two
// AI captures get a taller window instead.
const TALL = { desktop: { width: 1280, height: 1180 }, mobile: { width: 390, height: 1180 } }

// ---------------------------------------------------------------------------
// API

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

/** Delete the demo account if it survived a previous run, then create it. See
 *  the warning in the header: seeding is additive, and a second helping of
 *  every meal is not visible in any single screenshot -- it shows up as
 *  figures that are all individually plausible and collectively wrong. */
async function authenticate() {
  const headers = { 'Content-Type': 'application/json' }
  const credentials = JSON.stringify({ email: EMAIL, password: PASSWORD })

  const login = await apiJson('/api/auth/login', { method: 'POST', headers, body: credentials })
  if (login.status === 200) {
    await apiJson('/api/auth/account', {
      method: 'DELETE',
      headers: { ...headers, Authorization: `Bearer ${login.body.access_token}` },
      body: JSON.stringify({ password: PASSWORD }),
    })
  }

  const signup = await apiJson('/api/auth/signup', { method: 'POST', headers, body: credentials })
  if (signup.status === 201) return signup.body.access_token
  throw new Error(`could not create ${EMAIL}: signup ${signup.status}`)
}

/** ⚠ LOCAL date parts, never toISOString().
 *
 *  A meal date is user-facing, and the server buckets it on ITS OWN local date
 *  while the dashboard asks for the local one. toISOString() gives the UTC
 *  date, so on a machine east of UTC in the evening every seeded day lands one
 *  behind -- and "today" becomes yesterday, leaving the dashboard's rings and
 *  meal list empty in the captures, silently, and only between certain hours. */
const isoDaysAgo = (days) => {
  const day = new Date()
  day.setDate(day.getDate() - days)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

// ---------------------------------------------------------------------------
// Seed data. Real food names and plausible macros: this is what a reader sees.

const MENUS = [
  [
    ['Overnight oats with blueberries', 526, 27, 72, 14],
    ['Chicken, basmati rice & broccoli', 765, 65, 82, 16],
    ['Greek yoghurt with honey', 260, 25, 30, 5],
    ['Salmon, new potatoes & green beans', 798, 55, 59, 35],
  ],
  [
    ['Scrambled eggs on sourdough', 578, 34, 48, 27],
    ['Chicken shawarma wrap', 863, 56, 78, 32],
    ['Apple and peanut butter', 331, 10, 34, 19],
    ['Beef mince with pasta', 880, 58, 89, 32],
  ],
  [
    ['Protein shake with banana', 423, 43, 48, 6],
    ['Tuna pasta salad', 685, 51, 72, 18],
    ['Cottage cheese with pineapple', 245, 28, 22, 4],
    ['Grilled halloumi & couscous bowl', 820, 41, 79, 38],
  ],
  [
    ['Greek yoghurt, granola & berries', 495, 30, 60, 14],
    ['Turkey and avocado sandwich', 718, 48, 64, 28],
    ['Handful of almonds', 223, 8, 8, 19],
    ['Chicken curry with rice', 928, 60, 98, 30],
  ],
  [
    ['Two boiled eggs and toast', 440, 26, 38, 20],
    ['Lentil soup with bread', 608, 30, 85, 15],
    ['Skyr with strawberries', 215, 26, 21, 1],
    ['Steak, sweet potato & salad', 898, 65, 68, 38],
  ],
]

const LIBRARY = [
  ['Chicken breast, raw', 100, 165, 31, 0, 3.6],
  ['Basmati rice, dry', 100, 356, 8.1, 78, 0.9],
  ['Rolled oats', 40, 152, 5.4, 26, 3],
  ['Greek yoghurt 0%', 170, 100, 17, 6, 0],
  ['Salmon fillet, raw', 100, 208, 20, 0, 13],
  ['Olive oil', 14, 119, 0, 0, 13.5],
  ['Whole egg, large', 58, 78, 6.3, 0.6, 5.3],
  ['Skyr, natural', 150, 96, 17, 6, 0.3],
  ['Almonds', 30, 174, 6.4, 6.1, 15],
  ['Sweet potato, raw', 100, 86, 1.6, 20, 0.1],
]

// More than the six the dashboard shows before folding the rest away, so Quick
// log is captured with both the collapsed grid and the control that expands it.
const TEMPLATES = [
  ['Overnight oats with blueberries', 526, 27, 72, 14],
  ['Chicken, basmati rice & broccoli', 765, 65, 82, 16],
  ['Protein shake with banana', 423, 43, 48, 6],
  ['Greek yoghurt with honey', 260, 25, 30, 5],
  ['Scrambled eggs on sourdough', 578, 34, 48, 27],
  ['Tuna pasta salad', 685, 51, 72, 18],
  ['Salmon, new potatoes & green beans', 798, 55, 59, 35],
  ['Handful of almonds', 223, 8, 8, 19],
]

const SUPPLEMENTS = [
  ['Creatine monohydrate', '5 g', ['08:00']],
  ['Vitamin D3', '2000 IU', ['08:00']],
  ['Omega-3', '1000 mg', ['08:00', '20:00']],
  ['Magnesium glycinate', '200 mg', ['22:00']],
]

async function seed(token) {
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const post = (path, body) =>
    apiJson(path, { method: 'POST', headers, body: JSON.stringify(body) })

  for (const [name, serving_size, calories, protein, carbs, fat] of LIBRARY) {
    await post('/api/foods', { name, serving_size, calories, protein, carbs, fat })
  }
  for (const [name, calories, protein, carbs, fat] of TEMPLATES) {
    await post('/api/meal-templates', { name, calories, protein, carbs, fat, items: [] })
  }
  for (const [name, dose, times] of SUPPLEMENTS) {
    await post('/api/supplements', { name, dose, times, active: true })
  }

  for (let day = 0; day < SEED_DAYS; day += 1) {
    const date = isoDaysAgo(day)
    const menu = MENUS[day % MENUS.length]
    // Today is deliberately part-logged: two meals, not four. That is what a
    // real dashboard looks like at midday, and it is the case the weekly
    // review's "the week ends yesterday" rule exists for.
    const meals = day === 0 ? menu.slice(0, 2) : menu
    // The five menus rotate, so without this the calorie chart is a perfect
    // five-day sawtooth that reads as generated rather than logged. A
    // deterministic +/-6% keeps re-runs identical while breaking the period;
    // it is symmetric, so mean intake -- and the measured burn derived from
    // it -- is unmoved.
    const jitter = 1 + (((day * 37) % 13) - 6) / 100
    const vary = (n) => Math.round(n * jitter)
    for (const [name, calories, protein, carbs, fat] of meals) {
      await post('/api/meals', {
        date, name,
        calories: vary(calories), protein: vary(protein),
        carbs: vary(carbs), fat: vary(fat),
      })
    }
    // A weigh-in most days, but not every day -- a perfect streak is not what
    // the trend line was designed against, and the gaps are what make the
    // smoothing visible in the chart.
    if (day % 7 !== 3) {
      // ⚠ `day` counts BACKWARDS from today, so the drift term must be
      // POSITIVE for the trend to FALL: the oldest day is the heaviest.
      // Signed the other way this seeds a gain, and the measured burn, the
      // auto targets and the review's rate check all inverted with it.
      // 0.05 kg/day is 0.35 kg/week, the goal rate set below.
      const drift = 0.05 * day
      const noise = [0, 0.28, -0.19, 0.12, -0.3, 0.22, -0.08][day % 7]
      await post('/api/weights', { date, weight_kg: Number((82.9 + drift + noise).toFixed(1)) })
    }
    for (const ml of [350, 500, 500, 400, day % 3 === 0 ? 500 : 250]) {
      await post('/api/water', { date, ml })
    }
    await post('/api/steps', { date, steps: [11240, 8630, 13010, 6420, 9870, 12360, 7180][day % 7] })
  }

  // Last, and after the weigh-ins: targets_auto recomputes the four goals from
  // the profile on save, and it needs a weight to read. A profile written first
  // would store goals derived from no weigh-in at all.
  await apiJson('/api/settings', {
    method: 'PUT',
    headers,
    body: JSON.stringify({
      calorie_goal: 2100, protein_goal: 150, carbs_goal: 230, fat_goal: 70,
      track_carbs: true, track_fat: true, weight_unit: 'kg',
      height_cm: 179, birth_date: '1996-03-14', sex: 'male',
      activity_level: 'moderate', goal_rate_kg_per_week: -0.35,
      targets_auto: true, steps_goal: 9000,
    }),
  })

  // Tick a couple of today's doses, so the supplements card shows both states.
  const today = isoDaysAgo(0)
  const supplements = await apiJson('/api/supplements', { headers })
  for (const supplement of (supplements.body ?? []).slice(0, 2)) {
    await post('/api/supplements/log', {
      supplement_id: supplement.id, date: today, time: supplement.times[0],
    })
  }
}

// ---------------------------------------------------------------------------
// Browser

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

/** Served in place of a real analysis when the backend has no provider key.
 *  Every figure is internally consistent -- the three items' macros sum to the
 *  meal estimate -- because a screenshot of an estimate that does not add up
 *  is worse than no screenshot. */
const STAND_IN_ANALYSIS = {
  analysis_id: 1,
  meal_name: 'Grilled chicken with rice and salad',
  items: [
    { name: 'Grilled chicken breast', portion_grams: 165, calories: 272, protein: 51, carbs: 0, fat: 6, confidence: 'high', matched_food_name: 'Chicken breast, raw' },
    { name: 'Basmati rice, cooked', portion_grams: 180, calories: 234, protein: 4.7, carbs: 51, fat: 0.5, confidence: 'medium', matched_food_name: null },
    { name: 'Mixed salad with olive oil', portion_grams: 90, calories: 118, protein: 1.4, carbs: 4, fat: 11, confidence: 'low', matched_food_name: null },
  ],
  assumptions: [
    'Chicken weighed raw and grilled without added oil',
    '"A cup of rice" ≈ 180 g cooked',
    'About 1 tbsp of olive oil dressing on the salad',
  ],
  calories: { low: 560, estimate: 624, high: 710 },
  protein: { low: 52, estimate: 57.1, high: 61 },
  carbs: { low: 48, estimate: 55, high: 63 },
  fat: { low: 13, estimate: 17.5, high: 22 },
  confidence: 'medium',
  explanation:
    'The chicken is the confident part — it came from your library, so only the portion was estimated. The rice is a cup by eye, which is where most of the range comes from, and the dressing could be anywhere between a teaspoon and a tablespoon.',
  transcript: null,
  clarifying_question: null,
}

async function newContext(browser, token, seenIds, viewport, standIn) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 2 })
  await context.addInitScript(
    ([t, ids]) => {
      localStorage.setItem('macros_token', t)
      // ⚠ The real announcement ids, not a placeholder: the modal asks only
      // whether the key EXISTS, so junk sends it down the "unseen notes"
      // branch and it covers every capture.
      localStorage.setItem('macros_seen_announcements', JSON.stringify(ids))
    },
    [token, seenIds],
  )
  if (standIn) {
    await context.route('**/api/ai/analyze', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STAND_IN_ANALYSIS),
      }),
    )
  }
  return context
}

async function settle(page) {
  await page.waitForSelector('h1, h2', { timeout: 20_000 })
  await page.waitForLoadState('networkidle')
  // recharts tweens its lines in over ~1.5s; capture the finished state.
  await page.waitForTimeout(2200)
}

const AI_NOTE =
  'Grilled chicken breast, about 165 g, with a cup of basmati rice and a side salad with olive oil'

/** MealAnalyzer seeds `expanded` from the note draft in sessionStorage, so on a
 *  second visit the panel is ALREADY open and clicking the toggle would close
 *  it. Read the state, then act. */
async function ensureAnalyzerOpen(page) {
  const toggle = page.locator('button:has-text("Estimate macros with AI")')
  await page.waitForTimeout(300)
  if ((await toggle.count()) > 0) {
    await toggle.click()
    await page.waitForLoadState('networkidle')
  }
}

async function runAnalysis(page) {
  await ensureAnalyzerOpen(page)
  await page.fill('textarea', AI_NOTE)
  await page.click('button:has-text("Analyze")')
  // A real provider call retries a busy model for up to its deadline.
  await page.waitForSelector('button:has-text("Use these ingredients")', { timeout: 90_000 })
}

const SHOTS = [
  { key: 'dashboard', route: '/' },
  {
    key: 'log-meal',
    route: '/log',
    // The AI panel must be COLLAPSED here, and an earlier capture leaves a note
    // draft behind that opens it. Clear it, then load the page again.
    async before(page) {
      await page.evaluate(() => sessionStorage.clear())
    },
    async prep(page) {
      await page.fill('input[placeholder="Type a food name…"]', 'Chick')
      await page.waitForTimeout(900)
    },
  },
  {
    key: 'ai-analysis',
    route: '/log',
    async prep(page) {
      await runAnalysis(page)
      await page.waitForTimeout(600)
    },
    tall: true,
    // ⚠ The applied capture has to come from the SAME analysis, which is why
    // it hangs off this one rather than being a shot of its own. Two runs of
    // the model give two different estimates -- 612 kcal and 650 kcal on the
    // run that found this -- and the README shows the two images one after the
    // other, captioned as the same meal. It also halves the provider calls.
    then: {
      key: 'ai-applied',
      async prep(page) {
        await page.click('button:has-text("Use these ingredients")')
        await page.waitForTimeout(900)
        await page.locator('input[placeholder="Type a food name…"]').first().scrollIntoViewIfNeeded()
        await page.waitForTimeout(400)
      },
    },
  },
  { key: 'weight', route: '/weight' },
  { key: 'analytics', route: '/analytics' },
  { key: 'review', route: '/review' },
  { key: 'settings', route: '/settings/goals' },
]

async function capture(context, dir, kind, base) {
  await mkdir(dir, { recursive: true })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(`${kind}: ${error}`))
  for (const shot of SHOTS) {
    await page.setViewportSize(shot.tall ? TALL[kind] : base)
    if (shot.before) {
      await page.goto(`${BASE_URL}${shot.route}`, { waitUntil: 'domcontentloaded' })
      await shot.before(page)
    }
    await page.goto(`${BASE_URL}${shot.route}`, { waitUntil: 'domcontentloaded' })
    await settle(page)
    if (shot.prep) await shot.prep(page)
    await page.screenshot({ path: join(dir, `${shot.key}.png`) })
    console.log(`  ${kind}/${shot.key}.png`)
    if (shot.then) {
      await shot.then.prep(page)
      await page.screenshot({ path: join(dir, `${shot.then.key}.png`) })
      console.log(`  ${kind}/${shot.then.key}.png`)
    }
  }
  await page.close()
  return errors
}

/** Quantise in place if pngquant is available. Optional on purpose: a missing
 *  tool should cost file size, not the whole run. */
function compress(dir) {
  const keys = SHOTS.flatMap((shot) => (shot.then ? [shot.key, shot.then.key] : [shot.key]))
  const files = keys.flatMap((key) =>
    ['desktop', 'mobile'].map((kind) => join(dir, kind, `${key}.png`)),
  )
  try {
    execFileSync('pngquant', ['--quality=70-92', '--speed', '1', '--force', '--ext', '.png', ...files])
    console.log(`\ncompressed ${files.length} files with pngquant`)
  } catch {
    console.log('\npngquant not found or failed — images left uncompressed (about 3x larger)')
  }
}

// ---------------------------------------------------------------------------

const token = await authenticate()
console.log(`created ${EMAIL}`)
await seed(token)
console.log(`seeded ${SEED_DAYS} days`)

const status = await apiJson('/api/ai/status', { headers: { Authorization: `Bearer ${token}` } })
const standIn = !status.body?.configured
console.log(
  standIn
    ? 'no provider key on the backend — the two AI captures use a stand-in response'
    : `provider configured (${status.body.model}) — the AI captures are real analyses`,
)

const announcements = await apiJson('/api/announcements')
const seenIds = (announcements.body?.items ?? []).map((item) => item.id)

const chromium = await loadChromium()
const browser = await chromium.launch({ executablePath: findExecutable() })

const desktop = await newContext(browser, token, seenIds, DESKTOP, standIn)
const desktopErrors = await capture(desktop, join(outDir, 'desktop'), 'desktop', DESKTOP)
await desktop.close()

const mobile = await newContext(browser, token, seenIds, MOBILE, standIn)
const mobileErrors = await capture(mobile, join(outDir, 'mobile'), 'mobile', MOBILE)
await mobile.close()

await browser.close()
compress(outDir)

const errors = [...desktopErrors, ...mobileErrors]
if (errors.length) {
  console.error(`\n${errors.length} page errors:`)
  for (const error of errors) console.error(`  ${error}`)
  process.exit(1)
}
console.log('no page errors')
