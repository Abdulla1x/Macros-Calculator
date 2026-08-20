import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type { Settings } from '../types'

interface SettingsState {
  /** Null until the first fetch lands, and after one that failed. Pages treat
   *  it as "not known yet" and fall back to sensible defaults, exactly as they
   *  did when each fetched independently. */
  settings: Settings | null
  loading: boolean
  error: string | null
  /** Writes through to the API and updates every consumer with the row the
   *  server actually stored — not the optimistic local copy. */
  updateSettings: (next: Settings) => Promise<Settings>
  reload: () => void
}

const SettingsContext = createContext<SettingsState | null>(null)

/** One settings fetch for the whole authenticated app.
 *
 * Dashboard, LogMeal, Weight, Analytics and Settings each used to call
 * `api.getSettings()` on mount, so navigating between them re-fetched the same
 * row every time — five round trips against an instance that may still be
 * waking up. Worse, a goal edited on the Settings page left the Dashboard's
 * rings showing the old target until that page happened to remount.
 *
 * Analytics was missed by the original migration and kept its own fetch for two
 * further phases, which is why this list is now spelled out per page rather
 * than summarised: a comment that says the job is done is what stops the next
 * reader from checking. If a sixth page needs settings, it reads them here and
 * this sentence gets longer.
 *
 * Mounted inside RequireAuth so it never fires while logged out: the endpoint
 * is authenticated, and a 401 here would bounce the user to /login.
 *
 * `reload` exists for writes that change settings from outside this provider.
 * Saving a weigh-in is one: on an account with targets_auto on, the server
 * recomputes the four daily goals as a side effect, so Weight.tsx calls reload
 * to pick them up rather than letting the rings drift. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .getSettings()
      .then((next) => {
        if (!cancelled) {
          setSettings(next)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load settings.')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadCount])

  const updateSettings = useCallback(async (next: Settings) => {
    const saved = await api.updateSettings(next)
    // Deliberately not optimistic. The server is the authority on what was
    // stored, and a goal that silently differs from what the rings are drawn
    // against is the kind of wrong that nobody reports as a bug.
    setSettings(saved)
    setError(null)
    return saved
  }, [])

  const reload = useCallback(() => setReloadCount((count) => count + 1), [])

  return (
    <SettingsContext.Provider
      value={{ settings, loading, error, updateSettings, reload }}
    >
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings(): SettingsState {
  const state = useContext(SettingsContext)
  if (!state) throw new Error('useSettings must be used within SettingsProvider')
  return state
}
