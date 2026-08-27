// The colours and shapes every chart in this app shares.
//
// Spelled out here rather than read from index.css, and duplicated from it
// deliberately -- the same arrangement lib/limits.ts has with the server's
// bounds. The @theme tokens are the authority for anything a Tailwind utility
// can reach; these are the same values written again for the one place that
// cannot reach them.
//
// Why not var(--color-carbs): recharts takes most of these as SVG presentation
// attributes (stroke, fill) where var() is browser-dependent, and the rest as
// inline CSS (contentStyle) where it is not. Honouring the tokens would mean
// two spellings of one colour inside a single file. index.css says the same
// thing from its side, and scopes the job to this file by name.
//
// If a hue changes it must change in both places. Nothing asserts the pairing,
// which is the honest cost of a hand-written mirror.
//
// Admin.tsx had already done this privately -- axisTick, tooltipStyle and
// shortDate were consts in that one file. The names below are its names.

/** The card these charts are drawn on: --color-surface, slate-900. Used as the
 *  cut-out ring around an active dot so the halo reads against the card rather
 *  than against the series it belongs to. */
export const chartSurface = '#0f172a'

/** Axis lines: --color-line-strong, slate-700. */
export const axisStroke = '#334155'

/** Grid lines: --color-line, slate-800. */
export const gridStroke = '#1e293b'

/** The next surface up: --color-raised, slate-800. The tooltip panel floats on
 *  it, and MacroRing's unfilled track is drawn in it.
 *
 *  Identical to gridStroke today and kept as a separate name anyway, because
 *  index.css draws the same distinction: --color-line and --color-raised happen
 *  to hold one value, and a future retune that moves one has no reason to move
 *  the other. */
export const raisedSurface = '#1e293b'

/** Axis tick labels: --color-ink-faint. Passed by reference to every `tick=`
 *  prop in the app.
 *
 *  These were slate-500 (#64748b) until now -- the same value index.css retired
 *  from caption text for measuring 3.75:1 against surface and failing AA at 94
 *  sites. The accessibility pass that fixed those missed these, because a tick
 *  colour is a hex inside a prop and that pass worked by grepping class names.
 *  Axis labels are text and the 4.5:1 rule applies to them too.
 *
 *  ink-faint rather than ink-muted, which the legend below uses: at 5.12:1 on
 *  surface it clears AA while staying a step dimmer than the legend, so the
 *  chrome keeps the hierarchy it was drawn with. Charts sit directly on
 *  surface, so the nested-card blending that constrains this token elsewhere
 *  does not apply here.
 *
 *  RAW_COLOR below is still #64748b deliberately: it colours dots, not text,
 *  and 3.75:1 clears the 3:1 that non-text contrast asks for. */
export const axisTick = { fill: '#7c8aa3', fontSize: 11 }

/** The tooltip panel. Inline CSS rather than SVG attributes, so this one is a
 *  style object and not a set of props. */
export const tooltipStyle = {
  background: raisedSurface,
  border: `1px solid ${axisStroke}`,
  borderRadius: 8,
}

/** The tooltip's heading -- the date, above the values. slate-200. */
export const tooltipLabelStyle = { color: '#e2e8f0' }

/** Legend text: --color-ink-muted, slate-400. */
export const legendStyle = { fontSize: 12, color: '#94a3b8' }

/** The default plot box. Negative `left` claws back the gutter recharts
 *  reserves for a y-axis label none of these charts has. Analytics overrides
 *  it: its y-values run to four digits and need the room. */
export const chartMargin = { top: 5, right: 5, bottom: 0, left: -20 }

/** Rounded top corners only -- a bar sits on the axis, so its bottom corners
 *  are not corners. */
export const barRadius: [number, number, number, number] = [4, 4, 0, 0]

/** Drop the year, matching every other chart in the app. */
export const shortDate = (value: string) => value.slice(5)

/** The dot that appears under the cursor, ringed in the card colour so it
 *  reads as raised rather than as an extra data point. */
export const activeDot = (fill: string) => ({
  r: 5,
  fill,
  stroke: chartSurface,
  strokeWidth: 2,
})

/** Per-macro hues, mirroring --color-calories/protein/carbs/fat. Consumed both
 *  as recharts props and as the plain `color` string MacroRing takes. */
export const macroHues = {
  calories: '#f59e0b',
  protein: '#34d399',
  carbs: '#38bdf8',
  fat: '#fb7185',
} as const

/** Per-tracker hues, mirroring --color-water/steps/supplements. `water` is the
 *  same sky as `carbs` on purpose: they never share a chart, and forcing them
 *  apart would mean one of the two stopped matching its ring. Kept as separate
 *  names so that stays a decision rather than an accident. */
export const trackerHues = {
  water: '#38bdf8',
  steps: '#a78bfa',
  supplements: '#fbbf24',
} as const

// Emphasis form: the trend line is the subject, the raw weigh-ins are context.
// One accent hue plus the de-emphasis gray — validated against this app's chart
// surface (#0f172a) for lightness band, CVD separation and contrast.
export const TREND_COLOR = '#3b82f6'
export const RAW_COLOR = '#64748b'

// Validated against this app's chart surface (#0f172a) for lightness band,
// chroma, CVD separation and contrast. Blue and amber rather than the more
// obvious blue and green: blue/green is the worst possible pair under
// tritanopia (ΔE 5.7), where blue/amber separates at 28.7.
const ACTIVE_COLOR = '#3b82f6'
const SIGNUP_COLOR = '#d97706'
const MEALS_COLOR = '#0d9488'

/** Admin's three series. Namespaced rather than exported loose: ACTIVE_COLOR
 *  and TREND_COLOR are the same blue for unrelated reasons -- one is "accounts
 *  active today", the other "your weight trend" -- and a single shared name
 *  would make a later change to one silently move the other. */
export const adminHues = {
  active: ACTIVE_COLOR,
  signups: SIGNUP_COLOR,
  meals: MEALS_COLOR,
} as const
