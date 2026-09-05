import type {
  AdminStats,
  AdminUserRow,
  AIStatus,
  AnalyticsSummary,
  Announcements,
  BodyTargets,
  Calibration,
  CaloriePlan,
  CaloriePlanCreate,
  DaySurplus,
  Food,
  FoodCreate,
  HealthStatus,
  KeepWarmStatus,
  ImportResult,
  Meal,
  MealAnalysisResponse,
  MealCreate,
  MealTemplate,
  MealTemplateCreate,
  MessageResponse,
  OFFProduct,
  PlanDay,
  Settings,
  ReviewSummary,
  WeeklyReview,
  ShareCode,
  SharedMeal,
  StepDay,
  StepEntry,
  TokenResponse,
  Transcription,
  User,
  Supplement,
  SupplementDay,
  WaterDay,
  WaterEntry,
  WeightEntry,
  WeightEntryCreate,
  WeightTrend,
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

// fetch has no default timeout, so a request the server accepts and never
// answers leaves the spinner up forever — which reads as "the app is broken"
// rather than "try again".
//
// Every budget below has to clear a COLD START, because the free instance stops
// after 15 minutes without traffic and the next request pays for the whole boot.
// Measured on the live service: 52.5s, 52.6s, 52.7s and 64.0s across 2026 —
// call the ceiling ~65s. This was 60s, which is *inside* that range: a returning
// user with a stored token never sees the login page, so the warm-up ping in
// useWarmup never fires, and their first request — Layout's settings fetch —
// was being aborted by this constant on a server that was working perfectly.
// The keep-warm schedule removes that during the day, not outside it.
const DEFAULT_TIMEOUT_MS = 90_000
// The AI endpoints get their own budgets, which must EXCEED the backend's worst
// case, or the client aborts requests that were about to succeed. The server
// retries a busy provider for up to its deadline (60s analyze, 25s transcribe)
// and the final attempt can still run its full per-request timeout on top
// (30s / 12s), so the real ceilings are ~90s and ~37s — plus the upload.
//
// Plus a cold start on top of each, which is not paranoia: these are never a
// session's first request, but a tab left open for fifteen minutes gets a
// spun-down server on the next one, and composing a meal takes longer than that
// far more often than not.
const ANALYZE_TIMEOUT_MS = 180_000
const TRANSCRIBE_TIMEOUT_MS = 120_000
// Same arithmetic for the review summary: a 30s server deadline plus a final
// 15s attempt on top is a ~45s ceiling, and a cold instance adds to it.
const REVIEW_TIMEOUT_MS = 120_000

/** The headers every request carries.
 *
 * `extra` may override Content-Type -- that is how a caller sends something
 * other than JSON -- but never Authorization, which is applied last on purpose.
 * A FormData body sets no Content-Type at all: the browser has to add its own
 * multipart boundary, and naming the type here would destroy it.
 */
function authHeaders(
  isFormData: boolean,
  extra?: Record<string, string>,
): Record<string, string> {
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...extra,
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

/** An expired/invalid session on any data endpoint sends the user back to
 * login. Auth endpoints surface their 401s as normal form errors instead. */
function enforceAuth(path: string, status: number): void {
  if (status === 401 && !path.startsWith('/api/auth/')) {
    clearToken()
    window.location.assign('/login')
  }
}

/** Parsed JSON, or null when the body was not JSON at all. Both transports need
 * this before they can look for a `detail`, and neither should throw here --
 * an unreadable error body must still surface as the status code's error. */
function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

/** The error for a response that arrived and was not ok. */
function errorFrom(status: number, body: unknown): ApiError {
  let detail = `Request failed (${status})`
  const reported = (body as { detail?: unknown } | null)?.detail
  if (typeof reported === 'string') {
    detail = reported
  } else if (Array.isArray(reported)) {
    // FastAPI reports validation failures as an *array* of errors, never a
    // string, so the check above can never match a 422 — every one of them
    // used to surface as the generic "Request failed (422)" while the
    // server had already said exactly which field was wrong and why.
    // Forms guard their own inputs first; this is what is left when
    // something slips past one, and it has to name the field or the user
    // is left hunting through the whole page for it.
    const first = reported[0] as { msg?: unknown; loc?: unknown } | undefined
    if (typeof first?.msg === 'string') {
      const field = Array.isArray(first.loc) ? first.loc.at(-1) : undefined
      detail = typeof field === 'string' ? `${field}: ${first.msg}` : first.msg
    }
  }
  return new ApiError(detail, status)
}

/** The error for a request that never produced a response at all.
 *
 * A dead network, our own deadline, and a provider-level outage all land here.
 * status 0 marks "no HTTP response happened" so callers can still tell it apart
 * from a real 5xx.
 *
 * The third case is why this message must not blame the user's network. When
 * the host's edge answers 502/503 the response carries no CORS headers, so the
 * browser blocks it and the request fails before we ever see a status code — a
 * total outage is indistinguishable here from an unplugged cable. Observed for
 * real on 2026-08-20, when Render disabled spin-up for free services during a
 * Google Cloud incident and every user was told to check a connection that was
 * working perfectly.
 */
function transportError(timedOut: boolean): ApiError {
  return new ApiError(
    timedOut
      ? 'That took too long — the server may be waking up. Try again.'
      : 'Could not reach the server. It may be temporarily unavailable — ' +
        'check your connection, or try again in a few minutes.',
    0,
  )
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const headers = authHeaders(
    options.body instanceof FormData,
    options.headers as Record<string, string> | undefined,
  )

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (err) {
    throw transportError(err instanceof DOMException && err.name === 'TimeoutError')
  }

  if (!response.ok) {
    enforceAuth(path, response.status)
    const body = await response.text()
    throw errorFrom(response.status, parseJson(body))
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const api = {
  health: () => request<HealthStatus>('/api/health'),
  // Public: no auth header needed, so the status banner also works logged out.
  getAnnouncements: () => request<Announcements>('/api/announcements'),

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
  changePassword: (currentPassword: string, newPassword: string) =>
    request<TokenResponse>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  deleteAccount: (password: string) =>
    request<void>('/api/auth/account', {
      method: 'DELETE',
      body: JSON.stringify({ password }),
    }),
  // Both reset endpoints are public, but must stay under /api/auth/ so the 401
  // handling above surfaces failures as form errors instead of bouncing to
  // /login. A stale bearer token rides along automatically when one is stored;
  // the server ignores it on these two routes.
  forgotPassword: (email: string) =>
    request<MessageResponse>('/api/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, newPassword: string) =>
    request<void>('/api/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  getMeals: (date?: string) =>
    request<Meal[]>(`/api/meals${date ? `?date=${date}` : ''}`),
  createMeal: (meal: MealCreate) =>
    request<Meal>('/api/meals', { method: 'POST', body: JSON.stringify(meal) }),
  updateMeal: (id: number, meal: MealCreate) =>
    request<Meal>(`/api/meals/${id}`, { method: 'PUT', body: JSON.stringify(meal) }),
  deleteMeal: (id: number) =>
    request<void>(`/api/meals/${id}`, { method: 'DELETE' }),

  getMealTemplates: () => request<MealTemplate[]>('/api/meal-templates'),
  // An upsert on (user, lower(name)). Unlike saveFood, replacing a template
  // discards an ingredient list, so the response says which happened via
  // `created` and the caller words its message accordingly.
  saveMealTemplate: (template: MealTemplateCreate) =>
    request<MealTemplate>('/api/meal-templates', {
      method: 'POST',
      body: JSON.stringify(template),
    }),
  deleteMealTemplate: (id: number) =>
    request<void>(`/api/meal-templates/${id}`, { method: 'DELETE' }),

  // --- Meal codes ---------------------------------------------------------
  // A code IS the meal, not a link to it: see backend/app/share.py. Nothing is
  // stored server-side, so there is no code to delete and nothing to revoke.
  shareMeal: (id: number) => request<ShareCode>(`/api/share/meal/${id}`),
  shareMealTemplate: (id: number) => request<ShareCode>(`/api/share/template/${id}`),
  // POST for a pure read: a code runs to hundreds of characters, which strains
  // query-string limits, and a URL would be written to the edge access log.
  decodeMealCode: (code: string) =>
    request<SharedMeal>('/api/share/decode', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  // The whole library, unbounded and sorted by name -- what the Settings
  // editor lists. searchFoods below is the autocomplete's query and caps at 10,
  // which is right for a dropdown and wrong for "show me everything I have".
  getFoods: () => request<Food[]>('/api/foods'),
  searchFoods: (q: string) =>
    request<Food[]>(`/api/foods/search?q=${encodeURIComponent(q)}`),
  lookupOpenFoodFacts: (q: string) =>
    request<OFFProduct[]>(`/api/foods/lookup?q=${encodeURIComponent(q)}`),
  // An upsert on (user, lower(name)): the two callers that reach for this --
  // caching an Open Food Facts pick, and LogMeal's "save to library" tick --
  // hold a name and cannot know whether the row exists. updateFood is the
  // by-id edit, and the only way to rename without leaving the old row behind.
  saveFood: (food: FoodCreate) =>
    request<Food>('/api/foods', { method: 'POST', body: JSON.stringify(food) }),
  updateFood: (id: number, food: FoodCreate) =>
    request<Food>(`/api/foods/${id}`, { method: 'PUT', body: JSON.stringify(food) }),
  deleteFood: (id: number) =>
    request<void>(`/api/foods/${id}`, { method: 'DELETE' }),

  getWeights: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const query = params.toString()
    return request<WeightEntry[]>(`/api/weights${query ? `?${query}` : ''}`)
  },
  // An upsert on (user, date): re-saving a date replaces that day's entry and
  // still answers 200, so there is no "created vs updated" branch to handle.
  saveWeight: (entry: WeightEntryCreate) =>
    request<WeightEntry>('/api/weights', {
      method: 'POST',
      body: JSON.stringify(entry),
    }),
  deleteWeight: (id: number) =>
    request<void>(`/api/weights/${id}`, { method: 'DELETE' }),
  getWeightTrend: (days = 90) =>
    request<WeightTrend>(`/api/weights/trend?days=${days}`),

  // One request feeds the whole card: the day's entries, its total, and the
  // goal with the arithmetic behind it. The goal is resolved server-side, so
  // there is exactly one definition of it.
  getWaterDay: (date: string) =>
    request<WaterDay>(`/api/water?date=${encodeURIComponent(date)}`),
  // An insert, never an upsert — a second glass of water is a second glass.
  addWater: (date: string, ml: number) =>
    request<WaterEntry>('/api/water', {
      method: 'POST',
      body: JSON.stringify({ date, ml }),
    }),
  // What the card's undo button calls, on the newest entry.
  deleteWaterEntry: (id: number) =>
    request<void>(`/api/water/${id}`, { method: 'DELETE' }),

  // One request feeds the whole card: the count, the goal, and the walking
  // estimate with the weight it came from.
  getStepDay: (date: string) =>
    request<StepDay>(`/api/steps?date=${encodeURIComponent(date)}`),
  // An upsert, never an insert — reading the pedometer twice is the same day's
  // walking counted later, so this replaces rather than adds.
  saveSteps: (date: string, steps: number) =>
    request<StepEntry>('/api/steps', {
      method: 'POST',
      body: JSON.stringify({ date, steps }),
    }),
  // Back to never having been logged, which is not the same as saving a zero.
  clearSteps: (date: string) =>
    request<void>(`/api/steps?date=${encodeURIComponent(date)}`, {
      method: 'DELETE',
    }),

  // One request feeds the whole card: every scheduled dose for the day, and
  // which of them are ticked.
  // Calorie plans. getPlanDay is the one the dashboard rings depend on: it
  // returns the targets *in force* on a date, which is not what
  // getSettings() returns on any day a plan touches.
  getPlanDay: (date: string) =>
    request<PlanDay>(`/api/plan/day?date=${encodeURIComponent(date)}`),
  getPlans: () => request<CaloriePlan[]>('/api/plan'),
  getDaySurplus: (date: string) =>
    request<DaySurplus>(`/api/plan/surplus?date=${encodeURIComponent(date)}`),
  createPlan: (body: CaloriePlanCreate) =>
    request<CaloriePlan>('/api/plan', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  // Addressed by event date, not id — the group key is the plan's identity.
  cancelPlan: (eventDate: string) =>
    request<void>(`/api/plan/${encodeURIComponent(eventDate)}`, {
      method: 'DELETE',
    }),

  getSupplementDay: (date: string) =>
    request<SupplementDay>(
      `/api/supplements/day?date=${encodeURIComponent(date)}`,
    ),
  // Both check-off verbs return the whole day rather than the row, because the
  // tick list *is* the day's state and this is a card you tap several boxes on
  // in a row — a re-fetch after each one would double the requests against a
  // cold free-tier instance for no new information.
  //
  // Idempotent, both ways: ticking a ticked box and clearing a clear one are
  // the states the caller asked for, not errors.
  takeDose: (supplementId: number, date: string, time: string) =>
    request<SupplementDay>('/api/supplements/log', {
      method: 'POST',
      body: JSON.stringify({ supplement_id: supplementId, date, time }),
    }),
  untakeDose: (supplementId: number, date: string, time: string) => {
    const params = new URLSearchParams({
      supplement_id: String(supplementId),
      date,
      time,
    })
    return request<SupplementDay>(`/api/supplements/log?${params}`, {
      method: 'DELETE',
    })
  },

  // The management list, paused ones included — the Settings editor is the
  // only place a paused supplement can be brought back.
  getSupplements: () => request<Supplement[]>('/api/supplements'),
  createSupplement: (body: Omit<Supplement, 'id' | 'created_at'>) =>
    request<Supplement>('/api/supplements', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateSupplement: (id: number, body: Omit<Supplement, 'id' | 'created_at'>) =>
    request<Supplement>(`/api/supplements/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteSupplement: (id: number) =>
    request<void>(`/api/supplements/${id}`, { method: 'DELETE' }),

  getSettings: () => request<Settings>('/api/settings'),
  getBodyTargets: () => request<BodyTargets>('/api/settings/targets'),
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

  // `end` is the last day the review covers, and the caller passes its OWN
  // local yesterday. No timezone is stored for anyone and the server's today is
  // UTC, so letting the server pick would give the wrong week to everyone hours
  // off it. Same reason getAnalytics takes explicit dates.
  getReview: (end?: string) =>
    request<WeeklyReview>(`/api/review${end ? `?end=${end}` : ''}`),

  // Explicitly requested only -- it spends one provider call from a small daily
  // budget of its own. The window has to match the one the page is showing, or
  // the words would describe a different week from the numbers above them.
  phraseReview: (end?: string) =>
    request<ReviewSummary>(
      `/api/review/summary${end ? `?end=${end}` : ''}`,
      { method: 'POST' },
      REVIEW_TIMEOUT_MS,
    ),

  analyzeMeal: (form: FormData) =>
    request<MealAnalysisResponse>(
      '/api/ai/analyze',
      { method: 'POST', body: form },
      ANALYZE_TIMEOUT_MS,
    ),
  transcribeVoiceNote: (form: FormData) =>
    request<Transcription>(
      '/api/ai/transcribe',
      { method: 'POST', body: form },
      TRANSCRIBE_TIMEOUT_MS,
    ),
  // Operator diagnostic, not wired into any UI: answers "is the AI down, and
  // why" without a log dig. `probe` spends one provider call.
  getAIStatus: (probe = false) =>
    request<AIStatus>(`/api/ai/status${probe ? '?probe=true' : ''}`),
  getCalibration: () => request<Calibration>('/api/ai/calibration'),
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
  downloadExportAll: async () => {
    const data = await request<unknown>('/api/data/export/all')
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'macros_full_export.json'
    link.click()
    URL.revokeObjectURL(url)
  },
  importCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportResult>('/api/data/import', { method: 'POST', body: form })
  },
  // A two-column date,steps CSV. Deliberately not tuned to any one phone's
  // export — see the endpoint's docstring for why only a generic format is
  // honest here.
  importStepsCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportResult>('/api/data/import/steps', {
      method: 'POST',
      body: form,
    })
  },

  // Admin-only. These 403 for anyone not on the server's allowlist, and a 403
  // falls through the handler above as an ordinary ApiError — unlike a 401,
  // which bounces to /login. That difference is deliberate: a non-admin hitting
  // these is not logged out, they simply may not read them.
  getAdminStats: () => request<AdminStats>('/api/admin/stats'),
  getAdminUsers: (limit?: number) =>
    request<AdminUserRow[]>(
      `/api/admin/users${limit ? `?limit=${limit}` : ''}`,
    ),
  getKeepWarm: () => request<KeepWarmStatus>('/api/admin/keep-warm'),
}
