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
