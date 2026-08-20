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
}

export type MealCreate = Omit<Meal, 'id'>

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

export interface AnalyticsSummary {
  days: DayTotals[]
  totals: Record<string, number>
  averages: Record<string, number>
  /** Days in the range that actually have meals — the denominator the
   *  averages are built from. */
  logged_days: number
}

export interface ImportResult {
  inserted: number
  skipped_duplicates: number
  skipped_invalid: number
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
}
