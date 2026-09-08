// The browser-harness plumbing shared by scripts/dom-snapshot.mjs and
// scripts/a11y-audit.mjs: config, the route lists, chromium discovery, the
// seeded account, and the navigation loop that visits a route and waits for it
// to settle.
//
// It was extracted from dom-snapshot.mjs, which had grown ~250 lines that the
// accessibility audit needed verbatim. Importing that file was not an option --
// it reads process.argv at the top level and exits when it is missing.
//
// Everything here is a local verification tool. Nothing in it ships.
//
// ---------------------------------------------------------------------------
// Setup (once per machine)
//
//   1. From the repo root:  npm install --no-save playwright-core axe-core
//
//      ⚠ INSTALL THEM IN ONE COMMAND. There is no package.json at the repo
//      root, so npm treats each --no-save install list as the complete set of
//      dependencies and PRUNES everything else. Running
//      `npm install --no-save axe-core` on its own deletes playwright-core --
//      measured, not theorised: it reports "added 1 package, and removed 1
//      package" and leaves node_modules/ holding axe-core alone. Any future
//      tool has to join this line rather than get its own command.
//
//      Both are intentionally absent from frontend/package.json -- they are
//      verification tools, not something the app ships, and CI has no reason to
//      download a browser to run `npm ci`.
//
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
// ⚠ Start the backend with ADMIN_EMAILS set to the account's address, or /admin
// renders "Not found." instead of its two charts -- two of the five charts in
// the app, silently missing from whatever the caller is measuring.
//
// ---------------------------------------------------------------------------
// Environment
//
//   BASE_URL      frontend origin      (default http://localhost:5173)
//   API_URL       backend origin       (default http://localhost:8000)
//   EMAIL         account              (default snapshot@example.com)
//   PASSWORD      account password     (default snapshot-password-1)
//   CHROME_PATH   headless shell       (default: newest chromium_headless_shell
//                                       under ~/.cache/ms-playwright)
//   SEED_DAYS     days of data to seed (default 14)
//   SEED_TEMPLATES saved meals to seed  (default 8)
//   SEED_FOODS    library foods to seed (default 8)

import { readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

export const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'
export const API_URL = process.env.API_URL ?? 'http://localhost:8000'
export const EMAIL = process.env.EMAIL ?? 'snapshot@example.com'
export const PASSWORD = process.env.PASSWORD ?? 'snapshot-password-1'
export const SEED_DAYS = Number(process.env.SEED_DAYS ?? 14)
// More than the six the dashboard shows before folding the rest away, so the
// run covers the collapsed grid AND the control that expands it. Eight is the
// smallest number that does both.
export const SEED_TEMPLATES = Number(process.env.SEED_TEMPLATES ?? 8)
// ⚠ Before this the food library was seeded with NOTHING, so Settings -> Library
// rendered its empty state and the entire section -- every row, both source
// badges, the filter, the inline edit form, the add form -- had never once been
// compared. The fourth hole of this exact shape. Eight is more than
// COLLAPSED_ROWS, so the rows and the control that expands them are both covered.
export const SEED_FOODS = Number(process.env.SEED_FOODS ?? 8)

/** The seeded library, as real foods rather than a counter.
 *
 * ⚠ IT USED TO BE `Snapshot food ${n}` AT 100 g, AND THAT MADE TWO FEATURES
 * INVISIBLE AND ONE FALSE. Every generated name reduced to the same tokens, and
 * consecutive rows sat 15 kcal apart, so the duplicate detector matched all 28
 * pairs of them -- the seeded account would have opened the Library tab under a
 * wall of bogus cards. And every serving size was exactly 100, so the "Per
 * 100 g" button, which only appears on a row that is not, was never once in the
 * DOM. Both scripts would have been comparing a screen no real user sees.
 *
 * So the list is fixed and chosen: distinct foods that must NOT pair, ONE
 * deliberate near-duplicate pair, and two servings that are not 100 g. The pair
 * is the real one from the legacy single-user library -- 120 kcal/100 g against
 * 140 under two names -- which is also the pair app/duplicates.py's thresholds
 * were checked against.
 *
 * Both `source` badges are covered, and one row leaves carbs and fat unrecorded,
 * as the generated version did. The Open Food Facts row at 90 g is doing a third
 * job: converting it is the case where the badge must SURVIVE the rescale.
 */
const SEED_FOOD_CATALOGUE = [
  { name: 'Chicken breast, raw', serving_size: 100, calories: 165, protein: 31, carbs: 0, fat: 3.6, source: 'user' },
  { name: 'White rice, dry', serving_size: 100, calories: 360, protein: 7, carbs: 80, fat: 0.9, source: 'openfoodfacts' },
  { name: 'Free range hard boiled eggs', serving_size: 90, calories: 108, protein: 11.7, carbs: 0.6, fat: 7.8, source: 'openfoodfacts' },
  { name: 'Large White Eggs-Hard boiled', serving_size: 50, calories: 70, protein: 6, carbs: 0.4, fat: 5, source: 'openfoodfacts' },
  { name: 'Rolled oats', serving_size: 100, calories: 379, protein: 13.2, carbs: 67.7, fat: 6.5, source: 'user' },
  { name: 'Greek yogurt 0%', serving_size: 100, calories: 59, protein: 10, carbs: null, fat: null, source: 'user' },
  { name: 'Olive oil', serving_size: 100, calories: 884, protein: 0, carbs: 0, fat: 100, source: 'openfoodfacts' },
  { name: 'Almonds', serving_size: 100, calories: 579, protein: 21.2, carbs: 21.6, fat: 49.9, source: 'user' },
]

/** SEED_FOODS rows, from the catalogue and then from filler.
 *
 * The filler exists only so the env knob still means something above the
 * catalogue's length. Its calories are spread far wider than the duplicate
 * detector's tolerance so the extras cannot pair with each other or with the
 * catalogue -- the whole point of the list above is that exactly one pair is
 * reported. */
function seedFoods() {
  return Array.from({ length: SEED_FOODS }, (_, n) =>
    SEED_FOOD_CATALOGUE[n] ?? {
      name: `Filler food ${n}`,
      serving_size: 100,
      calories: 300 + n * 120,
      protein: 5 + n * 4,
      carbs: n % 2 === 0 ? 14 + n : null,
      fat: n % 2 === 0 ? 3 + n : null,
      source: n % 2 === 0 ? 'user' : 'openfoodfacts',
    },
  )
}

// Routes that render without a token. Kept in a separate context from the rest:
// nothing redirects an authenticated visitor away from /login, but visiting them
// signed out is what a signed-out visitor actually sees.
export const PUBLIC_ROUTES = ['/login', '/signup', '/forgot-password', '/reset-password']

// Everything behind RequireAuth. `/nope` is any unmatched address, which renders
// NotFound inside the Layout. There are no parameterised routes in this app, so
// this list is the whole surface.
//
// `/settings` is kept alongside its five panels on purpose: it is a redirect to
// /settings/goals, and visiting it is what would catch the redirect quietly
// breaking or landing somewhere else.
export const PRIVATE_ROUTES = [
  '/',
  '/log',
  '/weight',
  '/analytics',
  '/review',
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
export async function loadChromium() {
  try {
    return (await import('playwright-core')).chromium
  } catch {
    const url = new URL('../../node_modules/playwright-core/index.mjs', import.meta.url)
    return (await import(url.href)).chromium
  }
}

/** The headless shell, without hard-coding a build revision -- the number in
 *  the directory name moves with every playwright upgrade. */
export function findExecutable() {
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

export async function apiJson(path, init) {
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
export async function authenticate() {
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

/** ⚠ LOCAL dates, not toISOString().
 *
 *  A meal date is user-facing, and the server buckets it on ITS OWN local date
 *  while the dashboard asks for `localIsoDate()`. toISOString() gives the UTC
 *  date, so on a machine east of UTC during the evening every seeded day lands
 *  one behind -- and `isoDaysAgo(0)`, which is meant to be today, becomes
 *  yesterday. The dashboard's rings and meal list then render EMPTY, silently,
 *  and only between certain hours.
 *
 *  That makes the harness's coverage depend on the clock, which is the one
 *  thing a determinism harness must not do. Found on a UTC+4 machine at 23:37
 *  UTC while verifying the weekly review, whose window was short a day for the
 *  same reason. */
const isoDaysAgo = (days) => {
  const day = new Date()
  day.setDate(day.getDate() - days)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

/** Meals and weigh-ins for the last SEED_DAYS days, so every chart has
 *  something to draw, plus saved meals so the dashboard's Quick log renders.
 *  Values are a deterministic ramp, not random.
 *
 *  The templates matter as much as the charts: Quick log is hidden entirely
 *  until an account has one, so before this the whole section -- and every
 *  change ever made to it -- was outside the comparison.
 *
 *  ⚠ So do the body profile, the water logs and the steps goal, for exactly the
 *  same reason and found the same way. The weekly review shows a section only
 *  where the account has already opted into that thing -- a steps goal exists,
 *  water has been logged, the profile is complete enough to derive a burn -- so
 *  seeding meals alone left four of its eight checks permanently outside the
 *  comparison. That is the third time this harness has had a hole of this
 *  shape: Quick log (meal templates) and the AI panel (collapsed by default)
 *  were the first two. **A default state that renders nothing does not make a
 *  section inert, it makes it unwatched.** */
export async function seed(token) {
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  // The server takes `source` as given on POST -- it only overrides it on PUT --
  // so this is the one place a seeded account can produce an openfoodfacts row.
  for (const food of seedFoods()) {
    await apiJson('/api/foods', { method: 'POST', headers, body: JSON.stringify(food) })
  }
  for (let n = 0; n < SEED_TEMPLATES; n += 1) {
    await apiJson('/api/meal-templates', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        name: `Snapshot template ${n}`,
        calories: 400 + n * 25,
        protein: 30 + n,
        carbs: 40 + n,
        fat: 12 + n,
        items: [],
      }),
    })
  }
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
    // Alternating either side of the 2450 ml goal that 82.5 kg derives, so the
    // water check lands mid-range rather than at 0 or 7 -- a count stuck at an
    // extreme would not show a change in how it is rendered.
    await apiJson('/api/water', {
      method: 'POST',
      headers,
      body: JSON.stringify({ date, ml: day % 2 === 0 ? 2600 : 1200 }),
    })
    await apiJson('/api/steps', {
      method: 'POST',
      headers,
      body: JSON.stringify({ date, steps: day % 2 === 0 ? 11000 : 6000 }),
    })
  }

  // Last, and after the weigh-ins: targets_auto recomputes the four goals from
  // the profile on save, and it needs a weight to read. A profile written first
  // would store goals derived from no weigh-in at all.
  //
  // These values are what make /review's "targets" check say something rather
  // than refuse -- 14 weigh-ins over 14 days clears TDEE_MIN_WEIGH_INS and
  // TDEE_MIN_SPAN_DAYS, so the burn comes out measured rather than estimated.
  await apiJson('/api/settings', {
    method: 'PUT',
    headers,
    body: JSON.stringify({
      calorie_goal: 2000, protein_goal: 150, carbs_goal: 250, fat_goal: 70,
      track_carbs: true, track_fat: true, weight_unit: 'kg',
      height_cm: 180, birth_date: '1990-05-04', sex: 'male',
      activity_level: 'moderate', goal_rate_kg_per_week: -0.5,
      // ⚠️ ABOVE the seeded weigh-ins, not below, and that is not a typo.
      // The seed's day counter runs BACKWARDS from today, so `82.5 - day *
      // 0.05` puts the lightest reading furthest in the past and the trend
      // RISES towards today -- the same inversion that made a previous seed
      // report a gain while the comment claimed a loss. A goal of 78 against a
      // rising trend lands on 'moving_away', which draws the line but never a
      // date; 85 lands on 'on_course', the one status of the eight that has a
      // date in it and therefore the only one that puts every element of the
      // readout in front of these scripts.
      goal_weight_kg: 85,
      targets_auto: false, steps_goal: 10000,
    }),
  })
}

// Panels that render nothing until they are opened, and are therefore invisible
// to anything that only visits a route in its default state.
//
// /log's AI analyzer is collapsed to a single button until it is clicked, so
// its entire contents -- the description box, the photo picker, the library
// picker, the estimate card -- had never once been compared, and neither had
// any change ever made to them. That is the same hole meal templates left
// before this harness seeded them: an empty or collapsed state does not make a
// section inert, it makes it unwatched. Check what a default state hides before
// trusting any coverage claim made from these runs.
//
// A route may name several, applied in order -- /settings/food stacks two capped
// lists and an add form, and one selector cannot reach all three.
//
// An entry is either a selector to CLICK, or { fill, text } to type into. The
// typing form exists because the food autocomplete's dropdown cannot be clicked
// open: it appears only once two characters are in the field, so the entire
// suggestion list -- and the whole combobox rewrite that turned its rows into
// options -- was invisible to both scripts. That was the SIXTH time a default
// state has hidden a section here, and it was found the same way as the other
// five: by noticing after the fact that a change had produced no diff.
export const EXPAND_ON = {
  '/log': [
    'button:has-text("Estimate macros with AI")',
    // "egg" matches exactly the two seeded egg rows, in a fixed order (neither
    // is a prefix match, so /api/foods/search falls through to name order), so
    // the panel is deterministic. Two characters is the threshold; this clears
    // it. ⚠ It matches the CATALOGUE, so a SEED_FOODS below 4 opens no panel.
    { fill: 'input[placeholder="Type a food name…"]', text: 'egg' },
  ],
  // The weigh-in history caps at HISTORY_ROWS and hides the rest behind the
  // same toggle the library lists use. Matched on the plural noun, not the full
  // label, which carries a count that moves with SEED_DAYS.
  '/weight': ['button:has-text("weigh-ins")'],
  // Both lists render their first COLLAPSED_ROWS entries and hide the rest, and
  // "+ Add a food" opens a form that is otherwise never in the DOM -- the same
  // form this route exists to make findable. Matched on the plural nouns rather
  // than the full label, which carries a count that moves with SEED_FOODS.
  // "+ Add a food" is singular, so it cannot collide with "...foods".
  '/settings/food': [
    'button:has-text("foods")',
    'button:has-text("meals")',
    'button:has-text("Add a food")',
  ],
}

/** Open a page, walk `routes`, and hand each settled route to `onRoute`.
 *
 *  The waiting sequence is the part worth sharing: it took several rounds to
 *  get right and every caller needs exactly it. The page is closed when the
 *  walk finishes, so a caller gets one page per call rather than a shared one
 *  whose state leaks between routes. */
export async function visitRoutes(context, routes, onRoute) {
  const page = await context.newPage()
  for (const route of routes) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'domcontentloaded' })
    // The SPA commits the new route after navigation resolves, so waiting on
    // the URL alone reads the previous page. A heading is route-specific
    // content; networkidle then covers the data each page fetches for itself.
    await page.waitForSelector('h1, h2', { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    const expanders = [EXPAND_ON[route] ?? []].flat()
    for (const expander of expanders) {
      const selector = typeof expander === 'string' ? expander : expander.fill
      // Guarded rather than asserted: a route legitimately has no expander
      // before its data is seeded, and a hard failure there would make the
      // harness unusable on a fresh account.
      if ((await page.locator(selector).count()) === 0) continue
      if (typeof expander === 'string') {
        await page.locator(selector).click()
      } else {
        // Typed rather than filled: the field debounces on change, and fill()
        // sets the value in one event that the debounce never sees.
        await page.locator(selector).click()
        await page.locator(selector).type(expander.text, { delay: 30 })
      }
      // /log's panel fetches the food library when it opens, and the
      // autocomplete fetches again when it has two characters -- so wait, or the
      // caller races an empty picker or an empty list.
      await page.waitForLoadState('networkidle')
    }
    await onRoute(page, route)
  }
  await page.close()
}

/** Everything between "servers are up" and "a browser context is ready":
 *  authenticate, seed a fresh account, read the announcement ids, launch.
 *
 *  `anonymousContext` and `authedContext` differ only in that the second plants
 *  a token and the seen-announcement ids before any page script runs -- the
 *  token is read once at module load, and the announcements modal decides what
 *  to show on its first render.
 *
 *  ⚠ Seeding a junk value into macros_seen_announcements does not silence the
 *  modal. hasEverSeenAnnouncements() only asks whether the key EXISTS, so a
 *  junk array sends it down the "unseen notes" branch and it covers the page.
 *  These are the real ids from GET /api/announcements. */
export async function openSession({ log = console.log } = {}) {
  const { token, fresh } = await authenticate()
  log(`account ${EMAIL} (${fresh ? 'created' : 'existing'})`)
  if (fresh) {
    await seed(token)
    log(
      `seeded ${SEED_DAYS} days of meals, weigh-ins, water and steps, ` +
        `${SEED_TEMPLATES} templates, ${SEED_FOODS} library foods, ` +
        `and a complete body profile`,
    )
  }

  const announcements = await apiJson('/api/announcements')
  const seenIds = (announcements.body?.items ?? []).map((item) => item.id)

  const chromium = await loadChromium()
  const browser = await chromium.launch({ executablePath: findExecutable() })

  return {
    browser,
    token,
    fresh,
    anonymousContext: (viewport) => browser.newContext({ viewport }),
    authedContext: async (viewport) => {
      const context = await browser.newContext({ viewport })
      await context.addInitScript(
        ([sessionToken, ids]) => {
          localStorage.setItem('macros_token', sessionToken)
          localStorage.setItem('macros_seen_announcements', JSON.stringify(ids))
        },
        [token, seenIds],
      )
      return context
    },
  }
}
