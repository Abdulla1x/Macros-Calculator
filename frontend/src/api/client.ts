import type {
  AnalyticsSummary,
  Food,
  FoodCreate,
  ImportResult,
  Meal,
  MealAnalysisResponse,
  MealCreate,
  OFFProduct,
  Settings,
  TokenResponse,
  User,
} from '../types'
import { clearToken, getToken } from '../auth/token'

export const API_BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.body instanceof FormData
      ? {}
      : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!response.ok) {
    // An expired/invalid session on any data endpoint sends the user back to
    // login. Auth endpoints surface their 401s as normal form errors instead.
    if (response.status === 401 && !path.startsWith('/api/auth/')) {
      clearToken()
      window.location.assign('/login')
    }
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* keep generic message */
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const api = {
  signup: (email: string, password: string) =>
    request<TokenResponse>('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>('/api/auth/me'),

  getMeals: (date?: string) =>
    request<Meal[]>(`/api/meals${date ? `?date=${date}` : ''}`),
  createMeal: (meal: MealCreate) =>
    request<Meal>('/api/meals', { method: 'POST', body: JSON.stringify(meal) }),
  updateMeal: (id: number, meal: MealCreate) =>
    request<Meal>(`/api/meals/${id}`, { method: 'PUT', body: JSON.stringify(meal) }),
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

  analyzeMeal: (form: FormData) =>
    request<MealAnalysisResponse>('/api/ai/analyze', { method: 'POST', body: form }),
  linkAnalysis: (analysisId: number, mealId: number) =>
    request<void>(`/api/ai/analyses/${analysisId}`, {
      method: 'PATCH',
      body: JSON.stringify({ meal_id: mealId }),
    }),

  // A plain <a href> can't carry the Authorization header, so the CSV export
  // is fetched with auth and handed to the browser as a blob download.
  downloadExport: async () => {
    const token = getToken()
    const response = await fetch(`${API_BASE}/api/data/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new ApiError(`Export failed (${response.status})`, response.status)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'macros_backup.csv'
    link.click()
    URL.revokeObjectURL(url)
  },
  importCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportResult>('/api/data/import', { method: 'POST', body: form })
  },
}
