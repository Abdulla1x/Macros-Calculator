import { useOutletContext } from 'react-router-dom'
import type { Settings as SettingsType } from '../../types'

/** What the /settings layout hands each panel.
 *
 * Passed through <Outlet context> rather than a React context: there is exactly
 * one provider and one level of consumer, and the router already owns the
 * plumbing. It lives in its own .ts file because oxlint's
 * react/only-export-components warns on a *function* exported beside a
 * component -- allowConstantExport covers a const, not a hook.
 */
export interface SettingsPanel {
  /** The working copy, not the saved row. See the note in Settings.tsx on why
   *  edits are held back rather than published on every keystroke. */
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  /** Refuses an out-of-range value on blur and undoes it. Bind to onBlur. */
  guard: (field: keyof SettingsType) => () => void
  /** Raises the layout's refusal dialog. The sections that write straight to
   *  the server report their own bound violations through this too. */
  onRejected: (message: string) => void
  /** Bumped after every successful save so the derived-targets card refetches
   *  instead of sitting stale beside a fresh form. */
  targetsKey: number
}

export function useSettingsPanel(): SettingsPanel {
  return useOutletContext<SettingsPanel>()
}
