import { useCallback, useEffect, useRef, useState } from 'react'
import type { UploadHooks } from '../api/client'
import { api } from '../api/client'

/** What the app is waiting on, from the browser's point of view.
 *
 *   idle       nothing in flight
 *   uploading  the request body is still leaving this device -- a real number
 *   thinking   the bytes are gone and the server has not answered -- unknown
 *   waking     the server is asleep and booting, confirmed by a probe
 *
 * Separating `uploading` from `thinking` is the whole point of this hook. They
 * are one opaque wait today, they have entirely different causes, and only the
 * first of them can be measured.
 */
export type AnalysisPhase = 'idle' | 'uploading' | 'thinking' | 'waking'

/** How long an upload has to be running before its bar appears.
 *
 * Same idiom as BAR_AFTER_MS in useWakeProgress and COLD_START_NOTICE_AFTER_MS
 * in Layout: say nothing until the wait stops looking normal. Far shorter than
 * the cold start's 3s because the thing being explained is shorter -- on wifi a
 * small upload finishes in milliseconds, and a bar that appears and vanishes
 * reads as a glitch rather than as progress.
 */
const UPLOAD_BAR_AFTER_MS = 600

/** When to admit the model is taking a while.
 *
 * Timed from the END of the upload, not from the click. It used to run from the
 * click, which meant a phone on mobile data was told "the AI service is busy"
 * while it was still sending its own photos -- blaming the provider for the
 * user's uplink.
 */
const RETRY_NOTICE_AFTER_MS = 5_000

/** How long to wait before asking whether the server is even awake. */
const COLD_PROBE_AFTER_MS = 2_000

/** How long a health check may take before we call the server asleep.
 *
 * /api/health is DB-free -- asserted by test_health_check_touches_no_database,
 * not merely documented -- and answers in well under a second on a warm
 * instance. Two seconds is generous enough that a slow connection is not
 * mistaken for a boot.
 */
const COLD_PROBE_TIMEOUT_MS = 2_000

/** A probe that fails FASTER than this did not fail because of a boot.
 *
 * The same reasoning as COLD_START_FLOOR_MS in useWarmup: a server part-way
 * through a 52s boot leaves the request hanging, so a quick rejection means an
 * outage or a dead network instead. Claiming "waking up" then would be a
 * confident statement about the one thing the probe just failed to establish.
 */
const COLD_PROBE_FAILURE_FLOOR_MS = 1_500

/** How often to re-probe once the server is believed to be booting. Cheap: the
 * platform's own monitor already hits this route every ~4s. */
const COLD_PROBE_RETRY_MS = 5_000

export interface AnalysisProgressState {
  phase: AnalysisPhase
  /** Whether the upload has run long enough to be worth explaining. */
  showUpload: boolean
  /** Bytes-sent fraction in [0, 1], or null when the browser cannot size the
   * body. Some mobile browsers report `lengthComputable === false` and fire no
   * usable progress at all, which is a reason to say less rather than to
   * present a zero as though it were a measurement. */
  uploadFraction: number | null
  /** Whether the model has been thinking long enough to say so. */
  retrying: boolean
  /** When the body finished leaving the browser.
   *
   * The zero point for the cold-start bar, and the honest one: a sleeping
   * instance starts its boot on the request that wakes it, which is this one. */
  sentAt: number | null
}

export interface AnalysisProgressControls extends AnalysisProgressState {
  /** Begin a wait, and return the hooks to hand to api.analyzeMeal.
   *
   * `hasBody` is whether anything substantial is being uploaded; a note-only
   * analysis has nothing to show a bar for and goes straight to `thinking`.
   */
  start: (hasBody: boolean) => UploadHooks
  /** End it, however it ended. */
  finish: () => void
}

/** Live state for the AI analysis wait.
 *
 * Deliberately NOT modelled on useWakeProgress. That hook is a clock, and it is
 * entitled to be one because the boot was measured: ten samples, median
 * 52.303s, eight inside a 0.22s band. Nothing here has ever been measured, and
 * the duration depends on what was submitted -- four photos or none, a long
 * note or a word, ten attached foods or none -- so a curve fitted to a median
 * would describe no real analysis. What this hook reports instead is only what
 * it can observe: bytes leaving the device, and whether the server is awake.
 */
export function useAnalysisProgress(): AnalysisProgressControls {
  const [phase, setPhase] = useState<AnalysisPhase>('idle')
  const [fraction, setFraction] = useState<number | null>(null)
  const [barVisible, setBarVisible] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [sentAt, setSentAt] = useState<number | null>(null)

  // XHR events keep firing after the caller has moved on, so every run carries
  // an id and a late callback from an abandoned one is ignored. Without this a
  // stale onSent drags the UI back into `thinking` after it has gone idle.
  const runId = useRef(0)

  const start = useCallback((hasBody: boolean): UploadHooks => {
    const run = (runId.current += 1)
    setFraction(null)
    setBarVisible(false)
    setRetrying(false)
    if (hasBody) {
      setSentAt(null)
      setPhase('uploading')
    } else {
      setSentAt(Date.now())
      setPhase('thinking')
    }
    return {
      onProgress: (value) => {
        if (runId.current === run) setFraction(value)
      },
      onSent: () => {
        if (runId.current !== run) return
        setSentAt(Date.now())
        setPhase('thinking')
      },
    }
  }, [])

  const finish = useCallback(() => {
    runId.current += 1
    setPhase('idle')
    setBarVisible(false)
    setRetrying(false)
    setSentAt(null)
  }, [])

  // The flash guard. A short upload never renders a bar at all.
  useEffect(() => {
    if (phase !== 'uploading') return
    const timer = setTimeout(() => setBarVisible(true), UPLOAD_BAR_AFTER_MS)
    return () => clearTimeout(timer)
  }, [phase])

  // Whether the request is out of our hands and into the server's. Depending on
  // this rather than on `phase` keeps the effects below from tearing down and
  // re-arming every time the probe flips between thinking and waking -- which
  // is precisely when they must keep running.
  const waitingOnServer = phase === 'thinking' || phase === 'waking'

  // The "still trying" notice, started by the end of the upload rather than by
  // the click. That is the fix: the old timer ran during the upload too.
  useEffect(() => {
    if (!waitingOnServer) {
      setRetrying(false)
      return
    }
    const timer = setTimeout(() => setRetrying(true), RETRY_NOTICE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [waitingOnServer])

  // Is the server even awake? A long wait after the bytes are gone has two very
  // different causes -- a busy model, or a free instance that spun down and is
  // taking ~52s to boot -- and they deserve different words. /api/health is
  // cheap and DB-free, so asking beats guessing.
  //
  // Unmarked on purpose: only ?src=keepwarm counts as a scheduler ping, so this
  // can never inflate the /admin keep-warm figures.
  useEffect(() => {
    if (!waitingOnServer) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const probe = async () => {
      const started = Date.now()
      try {
        await api.health(COLD_PROBE_TIMEOUT_MS)
        if (!cancelled) setPhase('thinking')
      } catch {
        if (cancelled) return
        // A failure too fast to have been a boot says nothing about whether the
        // server is asleep, so the phase is left alone rather than upgraded
        // into a claim the probe did not support.
        if (Date.now() - started >= COLD_PROBE_FAILURE_FLOOR_MS) setPhase('waking')
      }
      if (!cancelled) timer = setTimeout(() => void probe(), COLD_PROBE_RETRY_MS)
    }

    timer = setTimeout(() => void probe(), COLD_PROBE_AFTER_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [waitingOnServer])

  return {
    phase,
    showUpload: phase === 'uploading' && barVisible,
    uploadFraction: phase === 'uploading' && barVisible ? fraction : null,
    retrying,
    sentAt,
    start,
    finish,
  }
}
