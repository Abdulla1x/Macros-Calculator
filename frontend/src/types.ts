export interface User {
  id: number
  email: string
  /**
   * Whether the server put this account on the ADMIN_EMAILS allowlist.
   *
   * Decides only whether the client bothers rendering the admin page. Every
   * /api/admin request is authorized server-side and independently — a client
   * that forces this true gets a 403 and nothing else.
   */
  is_admin: boolean
}

export interface HealthStatus {
  status: string
}

export interface AIProbe {
  status:
    | 'ok'
    | 'rate_limited'
    | 'rejected'
    | 'upstream_5xx'
    | 'unreachable'
    | 'internal_error'
    | 'not_configured'
    | 'quota_exhausted'
  message: string | null
  latency_ms: number | null
  cached: boolean
  age_seconds: number | null
}

export interface AIStatus {
  configured: boolean
  model: string
  fallback_model: string | null
  sdk_version: string
  probe: AIProbe | null
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  user: User
}

export interface MessageResponse {
  detail: string
}

export type Sex = 'male' | 'female'

export type ActivityLevel =
  | 'sedentary'
  | 'light'
  | 'moderate'
  | 'active'
  | 'very_active'

export interface Settings {
  calorie_goal: number
  protein_goal: number
  carbs_goal: number
  fat_goal: number
  track_carbs: boolean
  track_fat: boolean
  /** Display preference only — weights are always sent and stored in kg. */
  weight_unit: 'kg' | 'lb'
  /** Body profile. All nullable: the app works with none of it set. */
  height_cm: number | null
  /** YYYY-MM-DD. The date, not an age — an age would go stale in place. */
  birth_date: string | null
  sex: Sex | null
  activity_level: ActivityLevel | null
  /** Signed kg/week: negative loses, positive gains, 0 maintains. */
  goal_rate_kg_per_week: number | null
  /** When true the four goals above are derived server-side, not typed. */
  targets_auto: boolean
  /** Daily water goal in ml. Null means "derive it from my weight" rather
   *  than "unset" — the server resolves it and reports which it did. */
  water_goal_ml: number | null
  /** Quick-add amounts in ml. Null means the server's shipped defaults, which
   *  is why the card falls back to DEFAULT_WATER_QUICK_ADDS rather than
   *  rendering no buttons. */
  water_quick_adds: number[] | null
  /** Daily step goal. Null means "no goal", NOT "derive one for me" — the
   *  opposite of water_goal_ml above, and the reason the steps card drops its
   *  progress bar entirely rather than drawing progress towards a default. */
  steps_goal: number | null
  /** "HH:MM", or null. A third meaning for an empty settings field, after the
   *  two above: null here means the weigh-in reminder is switched off. The
   *  time and the opt-in are one field on purpose — see models.py. */
  weigh_in_reminder_time: string | null
  /** How many days without a weigh-in before the nudge speaks. Never null:
   *  it cannot express "off", which is what keeps it from contradicting the
   *  field above. Kept while the reminder is off. */
  weigh_in_reminder_days: number
}

/** One logged drink. */
export interface WaterEntry {
  id: number
  date: string
  ml: number
  created_at: string | null
}

/** Where the day's goal came from, so the card can show its working.
 *
 * Same intent as TdeeBasis: a derived number arrives with its inputs attached,
 * and "we had nothing to derive from" is stated rather than dressed up as a
 * personal figure. */
export interface WaterGoalBasis {
  source: 'custom' | 'weight' | 'default'
  ml_per_kg: number | null
  weight_kg: number | null
}

/** One day of water — everything the card renders, in one response.
 *
 * The goal is computed server-side and travels with the total on purpose:
 * deriving it here would be a second definition of a number the app already
 * defines once. */
export interface WaterDay {
  date: string
  total_ml: number
  goal_ml: number
  goal_basis: WaterGoalBasis
  entries: WaterEntry[]
}

/** One day's step count, as stored. */
export interface StepEntry {
  id: number
  date: string
  steps: number
  created_at: string | null
}

/** One day of steps — everything the card renders, in one response.
 *
 * `logged` carries what `steps` cannot: zero is a legal count, so "logged a
 * zero" and "never logged" both report `steps: 0`, and only one of them should
 * offer a Clear button.
 *
 * There is no basis object beside `goal` the way WaterGoalBasis sits beside
 * `goal_ml`. A water goal is derived and has arithmetic worth showing; a step
 * goal is either a number the user typed or no number at all. */
export interface StepDay {
  date: string
  steps: number
  logged: boolean
  goal: number | null
  burn_kcal: number | null
  burn_weight_kg: number | null
}

/** One supplement the user keeps on their list.
 *
 * `times` is the schedule as "HH:MM" strings, sorted and de-duplicated by the
 * server. Strings rather than a time type because they are *labels on a
 * schedule*, not instants: no date, no timezone, and the two digits either side
 * of the colon are what the log row and the clock comparison both want.
 *
 * `active: false` means paused — off the daily card, history intact. It is the
 * non-destructive way to stop taking something; deleting takes every ticked
 * dose with it. */
export interface Supplement {
  id: number
  name: string
  dose: string | null
  times: string[]
  active: boolean
  created_at: string | null
}

/** One scheduled dose on one day, and whether it has been taken.
 *
 * `off_schedule` marks a slot that is only here because a dose was ticked in
 * it — the supplement has since been paused, or its time moved. It is history
 * rather than something due, and it is what stops pausing or rescheduling from
 * turning a day that was fully taken into a day with a miss on it. */
export interface SupplementSlot {
  supplement_id: number
  name: string
  dose: string | null
  time: string
  taken: boolean
  off_schedule: boolean
}

/** One day of doses — everything the card renders, in one response.
 *
 * Nothing here says whether a dose is *due*. That needs the user's wall clock,
 * which the server does not have and this app stores no timezone for, so it is
 * the one derived value among the daily trackers that is honestly the client's
 * to compute. See SupplementsCard. */
export interface SupplementDay {
  date: string
  taken: number
  scheduled: number
  slots: SupplementSlot[]
}

/** What a measured TDEE was built from, or what it is still short of. */
export interface TdeeBasis {
  logged_days: number
  weigh_ins: number
  span_days: number
  mean_intake: number | null
  trend_change_kg: number | null
  /** Null exactly when the measurement was used. */
  unavailable_reason: string | null
}

/** What the profile implies, and what is stopping it implying more.
 *
 * Most of these are derived rather than measured, which is why `weight_kg` and
 * `weight_date` travel with them — the input has to be visible beside the
 * conclusion. `tdee` is the exception once `tdee_source` is `measured`: it then
 * comes from this person's own logs rather than a formula, and `tdee_basis`
 * carries the sample it was taken from. `missing` names the absent profile
 * fields, so the UI can ask for the one that is blocking instead of rendering
 * an empty card. */
export interface BodyTargets {
  missing: string[]
  bmi: number | null
  bmr: number | null
  tdee: number | null
  target_calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  weight_kg: number | null
  weight_date: string | null
  clamped_reason: string | null
  /** Which method produced `tdee`. */
  tdee_source: 'estimated' | 'measured'
  /** The formula's answer, kept even when measurement won, so both can show. */
  tdee_estimated: number | null
  tdee_basis: TdeeBasis | null
}

export interface WeightEntry {
  id: number
  date: string
  weight_kg: number
}

export type WeightEntryCreate = Omit<WeightEntry, 'id'>

export interface WeightTrendPoint {
  date: string
  weight_kg: number
  /** The smoothed value the server computed; never recomputed client-side. */
  trend_kg: number
}

export interface WeightTrend {
  points: WeightTrendPoint[]
  latest_trend_kg: number | null
  /** Null when there are too few weigh-ins to fit a rate. */
  weekly_rate_kg: number | null
  point_count: number
}

export interface Meal {
  id: number
  date: string
  name: string
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  /**
   * When the row was last corrected; null if it never has been. Server-set --
   * hence the omit below. Widening `Meal` without widening that omit would
   * silently make this a required field on every create form.
   */
  updated_at: string | null
}

export type MealCreate = Omit<Meal, 'id' | 'updated_at'>

/** One ingredient row inside a saved template. */
export interface TemplateItem {
  name: string
  weight_grams: number
  serving_size: number
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
}

export interface MealTemplate {
  id: number
  name: string
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  /**
   * Empty for a template saved while editing an existing meal, which has only
   * a single pass-through row. Applying such a template falls back to its
   * totals — see rowsFromTemplate in LogMeal.
   */
  items: TemplateItem[]
  /**
   * False when the save replaced an existing template with the same name.
   * Only meaningful on a POST response; listing always reports false.
   */
  created: boolean
}

export type MealTemplateCreate = Omit<MealTemplate, 'id' | 'created'>

/** A meal encoded as a string, ready to hand to someone. */
export interface ShareCode {
  code: string
}

/**
 * A meal that arrived in a code.
 *
 * Structurally a MealTemplateCreate, deliberately: that is what lets
 * rowsFromTemplate apply it unchanged, including its fallback to a single
 * totals row when `items` is empty — which is exactly the case for a code made
 * from a logged meal, since meals do not keep their ingredient rows.
 *
 * Carries no id and no date. The date in a code would be when the *sender* ate
 * it, and the form defaults to the recipient's own day instead.
 */
export interface SharedMeal {
  name: string
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  items: TemplateItem[]
}

export interface Food {
  id: number
  name: string
  serving_size: number
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  source: 'user' | 'openfoodfacts'
}

export type FoodCreate = Omit<Food, 'id'>

export interface OFFProduct {
  name: string
  brand: string | null
  serving_size: number
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  source: 'openfoodfacts'
}

export interface DayTotals {
  date: string
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
}

/** The four macros, always all present.
 *
 *  routers/analytics.py builds these by looping over a fixed tuple of the four
 *  names, so every key is written on every response — a day with no carbs
 *  logged gets 0, not a missing key. Typed as Record<string, number> the
 *  compiler could not know that, and under noUncheckedIndexedAccess every read
 *  became `number | undefined`, pushing a non-null assertion onto each of five
 *  call sites to restate what the server already guarantees. Saying it once,
 *  here, is both shorter and true. */
export interface MacroTotals {
  calories: number
  protein: number
  carbs: number
  fat: number
}

/** How many days each macro's average was actually built from.
 *
 *  Fixed keys for the same reason MacroTotals has them — the server writes all
 *  four on every response. Separate from MacroTotals because these are sample
 *  sizes, not quantities: they are never formatted with a unit and never
 *  summed. calories and protein always equal `logged_days`, since a meal
 *  cannot be saved without them; carbs and fat are nullable and so can be
 *  lower. */
export interface MacroDayCounts {
  calories: number
  protein: number
  carbs: number
  fat: number
}

export interface AnalyticsSummary {
  days: DayTotals[]
  totals: MacroTotals
  averages: MacroTotals
  /** Days in the range that have any meal at all. */
  logged_days: number
  /** The per-macro denominators. No average should be rendered without the
   *  matching count beside it when the two disagree. */
  average_days: MacroDayCounts
}

export interface ImportResult {
  inserted: number
  skipped_duplicates: number
  skipped_invalid: number
}

/** One macro's range accuracy, and the sample behind it.
 *
 *  Every rate is null together. Below the minimum sample the counts still
 *  arrive, because "you are seven corrections away" is more useful than a bare
 *  refusal — `unavailable_reason` is null exactly when a rate was produced,
 *  the same contract TdeeBasis carries. */
export interface MacroCalibration {
  corrected: number
  covered: number
  coverage_pct: number | null
  coverage_low_pct: number | null
  coverage_high_pct: number | null
  median_abs_error_pct: number | null
  median_signed_error_pct: number | null
  unavailable_reason: string | null
}

export interface ConfidenceBucket {
  confidence: Confidence
  corrected: number
  covered: number
  coverage_pct: number | null
}

/** How the saved meals compare to the AI estimates behind them.
 *
 *  `accepted_unchanged` is not a success rate. It counts meals saved with
 *  nothing moved, which is equally consistent with trusting the number and with
 *  never checking it — so it must never be rendered as evidence of accuracy.
 *  Coverage is measured over the corrected rows only, which is why the two
 *  counts are reported separately rather than as one ratio. */
export interface Calibration {
  analyses: number
  linked: number
  unreadable: number
  accepted_unchanged: number
  corrected: number
  calories: MacroCalibration
  protein: MacroCalibration
  by_confidence: ConfidenceBucket[]
  unavailable_reason: string | null
}

export type Confidence = 'high' | 'medium' | 'low'

export interface AnalyzedItem {
  name: string
  portion_grams: number
  calories: number
  protein: number
  carbs: number | null
  fat: number | null
  confidence: Confidence
  /** Which attached library food this item is, echoed back by name. Null when
   *  the model estimated it, which is every item when nothing was attached. */
  matched_food_name: string | null
}

export interface MacroRange {
  low: number
  estimate: number
  high: number
}

export interface MealAnalysis {
  meal_name: string
  items: AnalyzedItem[]
  assumptions: string[]
  calories: MacroRange
  protein: MacroRange
  carbs: MacroRange | null
  fat: MacroRange | null
  confidence: Confidence
  explanation: string
  /** What the model heard, when a voice note was sent. Null otherwise. */
  transcript: string | null
  clarifying_question: string | null
}

export interface MealAnalysisResponse extends MealAnalysis {
  analysis_id: number
}

/** A voice note turned into text, for the user to edit before analysing. */
export interface Transcription {
  transcript: string
}

/** A release note. `id` is stable — it's what we store once it's dismissed. */
export interface Announcement {
  id: string
  date: string
  title: string
  body: string
}

export interface Announcements {
  /** Live outage/maintenance notice from the server env; usually null. */
  banner: string | null
  items: Announcement[]
}

/**
 * Admin metrics. Counts, dates and account identifiers only — these types
 * carry no meal, food or weight content, and that is a boundary rather than an
 * omission. See the module docstring of backend/app/routers/admin.py.
 */
export interface AdminDailyCount {
  date: string
  count: number
}

export interface AdminDailyActivity {
  date: string
  active_users: number
  meals: number
}

export interface AdminStats {
  total_users: number
  total_meals: number
  signups_7d: number
  signups_30d: number
  active_7d: number
  active_30d: number
  meals_7d: number
  ai_calls_today: number
  ai_global_daily_limit: number
  ai_calls_30d_by_kind: Record<string, number>
  /** Width of the two series below, so the client never assumes it. */
  window_days: number
  signups: AdminDailyCount[]
  activity: AdminDailyActivity[]
}

/** One day's effective calorie and macro targets — what its rings are drawn
 *  against, after any plan adjustment. Not the same as the four goals on
 *  `Settings`: those are the STORED numbers, these are the ones in force on a
 *  particular day. They differ on exactly the days a plan touches.
 *
 *  `calorie_delta` is null on an ordinary day rather than 0 — a day no plan
 *  touches and a day a plan moves by nothing are different, and only the
 *  second has anything to cancel. */
export interface PlanDay {
  date: string
  calorie_goal: number
  protein_goal: number
  carbs_goal: number
  fat_goal: number
  calorie_delta: number | null
  kind: PlanKind | null
  event_date: string | null
}

/** 'planned' is a day arranged in advance and funded by the others, so it has
 *  a row of its own. 'compensating' spreads a day that already ran over or
 *  under, and that day has NO row — the meals logged on it are the other side
 *  of the ledger. */
export type PlanKind = 'planned' | 'compensating'

export interface CaloriePlan {
  event_date: string
  kind: PlanKind
  created_at: string | null
  days: PlanDay[]
  /** Zero for a planned group by definition; shown so it can be checked
   *  rather than taken on trust. */
  total_delta: number
  /** False once every day in the plan is in the past, which is not the same
   *  as the plan not existing. */
  can_cancel: boolean
}

export interface CaloriePlanCreate {
  kind: PlanKind
  event_date: string
  /** The days that ABSORB the change, never including the event day. */
  dates: string[]
  /** Only meaningful for 'planned'. A compensating amount is measured from the
   *  meals server-side and anything sent here is ignored. */
  calorie_delta?: number | null
}

/** How far a finished day ran from the target it actually had.
 *
 *  Consumed and reference arrive separately rather than pre-subtracted because
 *  the reference is the weak half: this app stores no historical target, so it
 *  is what that day's target is *now*. The screen has to be able to say so. */
export interface DaySurplus {
  date: string
  consumed_calories: number
  reference_calories: number
  surplus_calories: number
  /** Zero means nobody logged that day, not that nobody ate. */
  meal_count: number
  calorie_delta: number | null
}

export interface AdminUserRow {
  id: number
  email: string
  created_at: string
  /** Null for an account that signed up and never logged anything. */
  last_active_at: string | null
  meals: number
  weights: number
  foods: number
  meal_templates: number
  ai_calls: number
  /** The daily trackers. Water counts drinks and supplement_logs counts doses,
   *  so both climb several times a day; steps counts *days* logged, since it
   *  upserts. Different units, which is why the table gives them a column each
   *  rather than one summed "activity" figure that would mean nothing. */
  water_logs: number
  steps: number
  supplements: number
  supplement_logs: number
  /** Adjusted *days*, not plans — one banked Saturday is four or five of these.
   *  Never the dates themselves: which day someone has plans on says nothing
   *  about health and a good deal about their life. */
  calorie_plan_days: number
}


/** One question the weekly review answers, and the sample behind the answer.
 *
 * `value` and `target` are the two numbers `detail` compares, carried beside
 * the sentence so the UI never parses prose to render a figure.
 *
 * `sample_days` is what THIS check was computed over, and it deliberately
 * differs between checks: the intake and protein figures cover the seven-day
 * window while the weight rate is fitted over the 28-day one the trend line
 * uses. A single window on the response would force one of them to lie.
 *
 * Every sentence is assembled server-side, in `app/review.py`, so that copy
 * this careful is covered by pytest — this app has no frontend tests. */
export interface ReviewCheck {
  key: string
  /** `note` is a check with no goal to be on or off track against, like where
   *  the daily burn came from. `unknown` is a refusal, and is the only status
   *  that carries an `unavailable_reason`. */
  status: 'on_track' | 'off_track' | 'note' | 'unknown'
  value: number | null
  target: number | null
  unit: string
  sample_days: number
  detail: string
  /** Non-null exactly when `status` is `unknown`. */
  unavailable_reason: string | null
}

/** The last seven complete days, and what the app can honestly say about them.
 *
 * A check the user has not opted into is ABSENT from `checks` rather than
 * present and empty — someone with no steps goal is never asked about steps. */
export interface WeeklyReview {
  window_start: string
  window_end: string
  logged_days: number
  checks: ReviewCheck[]
}
