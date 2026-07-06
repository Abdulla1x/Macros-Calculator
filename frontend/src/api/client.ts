import type {
  AnalyticsSummary,
  Food,
  FoodCreate,
  ImportResult,
  Meal,
  MealCreate,
  OFFProduct,
  Settings,
} from '../types'

export const API_BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers =
    options.body instanceof FormData
      ? options.headers
      : { 'Content-Type': 'application/json', ...options.headers }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* keep generic message */
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const api = {
  getMeals: (date?: string) =>
    request<Meal[]>(`/api/meals${date ? `?date=${date}` : ''}`),
  createMeal: (meal: MealCreate) =>
    request<Meal>('/api/meals', { method: 'POST', body: JSON.stringify(meal) }),
  deleteMeal: (id: number) =>
    request<void>(`/api/meals/${id}`, { method: 'DELETE' }),

  searchFoods: (q: string) =>
    request<Food[]>(`/api/foods/search?q=${encodeURIComponent(q)}`),
  lookupOpenFoodFacts: (q: string) =>
    request<OFFProduct[]>(`/api/foods/lookup?q=${encodeURIComponent(q)}`),
  saveFood: (food: FoodCreate) =>
    request<Food>('/api/foods', { method: 'POST', body: JSON.stringify(food) }),

  getSettings: () => request<Settings>('/api/settings'),
  updateSettings: (settings: Settings) =>
    request<Settings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  getAnalytics: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const query = params.toString()
    return request<AnalyticsSummary>(`/api/analytics/daily${query ? `?${query}` : ''}`)
  },

  exportUrl: `${API_BASE}/api/data/export`,
  importCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportResult>('/api/data/import', { method: 'POST', body: form })
  },
}
