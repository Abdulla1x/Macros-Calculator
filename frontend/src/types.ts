export interface User {
  id: number
  email: string
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

export interface Settings {
  calorie_goal: number
  protein_goal: number
  carbs_goal: number
  fat_goal: number
  track_carbs: boolean
  track_fat: boolean
  /** Display preference only — weights are always sent and stored in kg. */
  weight_unit: 'kg' | 'lb'
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
