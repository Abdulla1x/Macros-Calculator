export interface User {
  id: number
  email: string
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
  clarifying_question: string | null
}

export interface MealAnalysisResponse extends MealAnalysis {
  analysis_id: number
}
