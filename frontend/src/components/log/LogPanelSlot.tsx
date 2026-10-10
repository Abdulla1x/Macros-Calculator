import { lazy, Suspense, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { logScreen } from './logPanelUrl'

const loadPanel = () => import('./LogPanel')
const LogPanel = lazy(loadPanel)

/** Where the Log panel mounts, kept out of the first download.
 *
 *  The panel brings Radix's dialog machinery (focus trap, scroll lock, the
 *  outside-click layer): ~13 KB gzipped, which every first visit would pay
 *  before anyone taps Log. So it is fetched when the page is idle, and mounted
 *  the first time `?log` appears; after that it stays mounted, so its exit
 *  animation can play. A failed fetch (a deploy removed the file) throws to
 *  the route's error element, which reloads onto the new version with the
 *  panel still open (lib/staleChunk.ts). */
export default function LogPanelSlot() {
  const { search } = useLocation()
  const [wanted, setWanted] = useState(false)
  const open = logScreen(search) !== null
  // Set during render rather than in an effect, so a reload with ?log in the
  // address does not paint a frame without the panel first.
  if (open && !wanted) setWanted(true)

  useEffect(() => {
    // Safari has no requestIdleCallback; a short timeout is the usual stand-in.
    const idle = window.requestIdleCallback ?? ((run: () => void) => window.setTimeout(run, 1_500))
    idle(() => void loadPanel().catch(() => undefined))
  }, [])

  return wanted ? (
    <Suspense fallback={null}>
      <LogPanel />
    </Suspense>
  ) : null
}
