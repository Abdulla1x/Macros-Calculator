import type { AnalysisProgressState } from '../hooks/useAnalysisProgress'
import WakingNotice from './WakingNotice'

/** What is happening during an AI analysis, said as precisely as we can.
 *
 * Three states, because the wait has three causes and they are not
 * interchangeable:
 *
 *   uploading  a real percentage -- the only measured number in this whole wait
 *   waking     the server is asleep; the calibrated cold-start bar applies
 *   thinking   the model has it and we genuinely do not know how long
 *
 * The upload is deliberately NOT folded into a single 0-100% covering the whole
 * analysis. Doing that would have to assert what share of the wait the model
 * accounts for, and that has never been measured -- inventing it is exactly the
 * mistake useWakeProgress's own comments warn against, run in reverse.
 */
/** A bar that moves without meaning anything, for the waits we cannot measure.
 *
 * aria-hidden with no progressbar role: an indeterminate bar carries nothing
 * the sentence beside it does not already carry, and a progressbar with no
 * value would only add noise to a screen reader.
 *
 * This is where motion-reduce differs from WakingNotice, deliberately. There
 * the movement encodes elapsed time against a measured boot, so the steps are
 * kept and only the tween is dropped. Here the sweep encodes nothing at all, so
 * under reduced motion it goes entirely and the sentence carries the whole
 * meaning -- a frozen sliver would read as a hang, and a full bar as done.
 */
function IndeterminateBar() {
  return (
    <span
      aria-hidden="true"
      className="mt-2 block h-1 overflow-hidden rounded-full bg-brand/20 motion-reduce:hidden"
    >
      <span className="block h-full w-1/4 animate-indeterminate rounded-full bg-brand" />
    </span>
  )
}

export default function AnalysisProgress({ state }: { state: AnalysisProgressState }) {
  const { phase, showUpload, uploadFraction, retrying, sentAt } = state

  if (phase === 'waking') {
    // The one place a calibrated curve is honest here: a sleeping instance
    // starts its boot on the request that wakes it, so the measured 52.3s
    // applies from the moment our bytes landed. Reusing the component means the
    // two explanations of a cold start can never drift apart.
    return (
      <WakingNotice className="mt-3 text-xs text-ink-faint" startedAt={sentAt ?? undefined} />
    )
  }

  if (phase === 'uploading') {
    if (!showUpload) return null
    // No measurable fraction: the browser could not size the body. Saying that
    // something is being sent is still true and still useful; a 0% that never
    // moves would be neither.
    if (uploadFraction === null) {
      return (
        <p className="mt-3 text-sm text-ink-muted">
          Sending your photos…
          <IndeterminateBar />
        </p>
      )
    }
    const percent = Math.round(uploadFraction * 100)
    return (
      <p className="mt-3 text-sm text-ink-muted">
        Sending your photos — {percent}%
        {/* A real measurement, so it gets a real progressbar with a value.
            Spans rather than divs because this sits inside a <p>. Not a live
            region: a percentage that changes continuously must never be
            announced. */}
        <span
          role="progressbar"
          aria-label="Upload progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-2 block h-1 overflow-hidden rounded-full bg-brand/20"
        >
          {/* motion-reduce drops the tween but keeps the steps, as WakingNotice
              does: the movement is information, only its smoothing is
              decoration. */}
          <span
            className="block h-full rounded-full bg-brand transition-[width] duration-200 ease-linear motion-reduce:transition-none"
            style={{ width: `${percent}%` }}
          />
        </span>
      </p>
    )
  }

  if (phase !== 'thinking') return null

  return (
    <p className="mt-3 text-sm text-ink-muted">
      {retrying
        ? 'The AI service is busy — still trying. This can take up to a minute.'
        : 'Analyzing — the bytes are sent, the model is working on it.'}
      <IndeterminateBar />
    </p>
  )
}
