import type { AnalysisProgressState } from '../../hooks/useAnalysisProgress'
import { DoneIcon } from '@/ui/icons'
import WakingNotice from '../WakingNotice'

type Stage = { label: string; detail?: string; state: 'done' | 'now' | 'wait'; bar?: number | null }

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`

/** What the estimate is doing while you wait (DESIGN.md: AI estimate, "honest
 *  stages, no fake percentage").
 *
 *  Only what the app can actually observe gets a stage of its own:
 *
 *    Sending N photos   the upload, with a real percentage: the one measured
 *                       number in the whole wait
 *    Estimating ...     the model has it; how long is genuinely unknown, so no
 *                       bar, only a line that changes when it runs long
 *    Waking the server  confirmed by a probe, with the calibrated boot bar
 *
 *  The prototype also showed "Reading your note" and "Using 1 of your saved
 *  foods" as steps that tick off in turn. The app cannot see when the model does
 *  either, so ticking them on a timer would be a progress bar made of guesses,
 *  the thing this component exists not to be. What the estimate is built from is
 *  said once, in the estimating line, instead. */
export default function EstimateStages({
  state,
  photos,
  hasNote,
  savedFoods,
}: {
  state: AnalysisProgressState
  photos: number
  hasNote: boolean
  savedFoods: number
}) {
  const { phase, uploadFraction, retrying, sentAt } = state
  if (phase === 'idle') return null

  const sources = [
    hasNote && 'your note',
    photos > 0 && plural(photos, 'photo', 'photos'),
    savedFoods > 0 && plural(savedFoods, 'saved food', 'saved foods'),
  ].filter(Boolean) as string[]
  const from =
    sources.length > 1 ? `${sources.slice(0, -1).join(', ')} and ${sources[sources.length - 1]}` : sources[0]

  const stages: Stage[] = []
  if (photos > 0) {
    stages.push({
      label: `Sending ${plural(photos, 'photo', 'photos')}`,
      state: phase === 'uploading' ? 'now' : 'done',
      bar: phase === 'uploading' ? uploadFraction : undefined,
    })
  }
  stages.push({
    label: from ? `Estimating from ${from}` : 'Estimating',
    // Said only once the wait stops looking normal (useAnalysisProgress). Wry
    // in small doses (DESIGN.md Voice), and still says what to expect.
    detail: retrying ? "Still looking. This one's got layers. Busy days can take up to a minute." : undefined,
    state: phase === 'uploading' ? 'wait' : 'now',
  })

  return (
    <div className="grid gap-3">
      <ol className="grid gap-3">
        {stages.map((stage) => (
          <li key={stage.label} className={`flex items-start gap-3 text-body ${stage.state === 'wait' ? 'text-ink-2' : ''}`}>
            <span aria-hidden="true" className="mt-0.5 grid size-[22px] shrink-0 place-items-center">
              {stage.state === 'done' ? (
                <DoneIcon size={16} weight="bold" />
              ) : stage.state === 'now' ? (
                // Under reduced motion the loop stops and the ring stays, so it
                // still reads as busy (DESIGN.md: loops stop, nothing vanishes).
                <span className="size-[18px] rounded-full border-[2.5px] border-action border-r-transparent motion-safe:animate-spin" />
              ) : (
                <span className="size-[14px] rounded-full border-[1.5px] border-rule" />
              )}
            </span>
            <span className="grid min-w-0 flex-1 gap-1">
              <span>
                {stage.label}
                <span className="sr-only">{stage.state === 'done' ? ', done' : stage.state === 'now' ? ', in progress' : ''}</span>
              </span>
              {stage.detail && <span className="text-small text-ink-2">{stage.detail}</span>}
              {/* A real measurement, so a real progressbar with a value. Not a
                  live region: a percentage that changes continuously must
                  never be announced. Absent until the upload has run long
                  enough to be worth a bar (useAnalysisProgress). */}
              {stage.bar != null && (
                <span
                  role="progressbar"
                  aria-label="Upload progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(stage.bar * 100)}
                  className="block h-1.5 overflow-hidden bg-track"
                >
                  <span
                    className="block h-full bg-action transition-[width] duration-200 ease-linear motion-reduce:transition-none"
                    style={{ width: `${Math.round(stage.bar * 100)}%` }}
                  />
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
      {/* The one place a calibrated curve is honest here: a sleeping server
          starts its boot on the request that wakes it, so the measured boot
          time applies from the moment the bytes landed. */}
      {phase === 'waking' && <WakingNotice className="text-small text-ink-2" startedAt={sentAt ?? undefined} />}
      <p className="text-small text-ink-2">
        You can close this and keep using the app. The Log button shows it's still working.
      </p>
    </div>
  )
}
