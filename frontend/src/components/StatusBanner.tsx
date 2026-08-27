import { useEffect, useState } from 'react'
import { dismissBanner, isBannerDismissed } from '../lib/dismissals'
import Card from './ui/Card'

/** The live status notice, when the server has one set.
 *
 * Presentational: the text comes from whoever already fetched
 * `/api/announcements`, so the logged-in shell and the login page can each show
 * it without a second request.
 *
 * The role="status" wrapper is rendered unconditionally, even with no banner.
 * That is the whole point: a live region has to be in the DOM *before* its
 * content arrives, or assistive technology has nothing to observe. The banner
 * always arrives from an async fetch, so returning null until it lands — which
 * is what this component used to do — meant the notice was never announced.
 * Checked before doing this: none of the five call sites uses space-y-*, so an
 * extra always-present child cannot silently eat a sibling's margin. */
export default function StatusBanner({ banner }: { banner: string | null }) {
  const [dismissed, setDismissed] = useState(false)

  // A banner that arrives (or changes) after mount has to be re-checked, or a
  // new notice would stay hidden behind the previous one's dismissal.
  useEffect(() => {
    setDismissed(banner !== null && isBannerDismissed(banner))
  }, [banner])

  return (
    <div role="status" aria-live="polite">
      {banner && !dismissed && (
        <Card tone="warn" pad="none" className="mb-4 flex items-start gap-3 px-4 py-3 text-sm">
          <span aria-hidden="true">⚠️</span>
          <p className="flex-1">{banner}</p>
          <button
            onClick={() => {
              dismissBanner(banner)
              setDismissed(true)
            }}
            aria-label="Dismiss notice"
            className="shrink-0 text-amber-300/70 hover:text-amber-100"
          >
            ✕
          </button>
        </Card>
      )}
    </div>
  )
}
