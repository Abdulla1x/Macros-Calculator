import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Calibration, MacroCalibration } from '../types'
import Card from './ui/Card'

const round = (value: number) => Math.round(value)

/** One macro's answer, or the reason there isn't one yet.
 *
 *  The refusal is per-macro on purpose: protein and calories fill up at very
 *  different speeds, so a single section-wide "not enough data" would sit
 *  directly above a real number and contradict it. */
function MacroCard({ label, macro }: { label: string; macro: MacroCalibration }) {
  const measured = macro.coverage_pct !== null

  return (
    <Card pad="sm" tone="sunken">
      <p className="text-xs text-slate-400">{label}</p>

      {measured ? (
        <>
          <p className="mt-1 text-xl font-bold">
            {round(macro.coverage_pct as number)}%
            <span className="ml-2 text-xs font-normal text-slate-400">landed in range</span>
          </p>
          {/* The interval, not just the point. A coverage rate is itself an
              estimate from a small sample, and printing it bare would be the
              same false precision this section exists to expose. */}
          {macro.coverage_low_pct !== null && (
            <p className="mt-1 text-xs text-ink-faint">
              plausibly {round(macro.coverage_low_pct)}–{round(macro.coverage_high_pct as number)}%,
              from {macro.corrected} correction{macro.corrected === 1 ? '' : 's'}
            </p>
          )}
          {macro.median_signed_error_pct !== null && (
            <p className="mt-2 text-xs text-slate-400">
              You typically moved the number{' '}
              <span className="font-semibold text-slate-200">
                {macro.median_signed_error_pct >= 0 ? 'up' : 'down'}{' '}
                {round(Math.abs(macro.median_signed_error_pct))}%
              </span>
            </p>
          )}
        </>
      ) : (
        <>
          <p className="mt-1 text-xl font-bold text-ink-faint">—</p>
          <p className="mt-1 text-xs text-ink-faint">{macro.unavailable_reason}</p>
        </>
      )}
    </Card>
  )
}

export default function CalibrationSection() {
  const [data, setData] = useState<Calibration | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let stale = false
    setLoading(true)
    setError(null)
    api
      .getCalibration()
      .then((result) => {
        if (!stale) setData(result)
      })
      .catch((err) => {
        if (stale) return
        setData(null)
        setError(err instanceof Error ? err.message : 'Could not load estimate accuracy.')
      })
      .finally(() => {
        if (!stale) setLoading(false)
      })
    return () => {
      stale = true
    }
  }, [attempt])

  return (
    <Card as="section">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="font-semibold">How close were the AI's estimates?</h2>
        {data && data.linked > 0 && (
          <p className="text-xs text-slate-400">
            {data.linked} meal{data.linked === 1 ? '' : 's'} saved from an estimate
          </p>
        )}
      </div>
      <p className="mb-4 text-xs text-slate-400">
        Measured against the numbers you saved, which are your best information rather than a
        lab result — so this is how far you moved the AI's estimate, not how wrong it was.
      </p>

      {loading ? (
        <p className="py-6 text-center text-sm text-ink-faint">Checking…</p>
      ) : error ? (
        <div className="rounded-lg border border-rose-900/60 p-4 text-center">
          <p className="text-sm text-rose-300">{error}</p>
          <button
            onClick={() => setAttempt((n) => n + 1)}
            className="mt-2 rounded-lg border border-slate-700 px-3 py-1 text-xs hover:border-emerald-500 hover:text-emerald-300"
          >
            Retry
          </button>
        </div>
      ) : !data || data.linked === 0 ? (
        <p className="py-6 text-center text-sm text-ink-faint">
          Nothing to compare yet. Analyse a meal, tap “Use these ingredients”, and save it — the
          app will start keeping score of itself here.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            <MacroCard label="Calorie range" macro={data.calories} />
            <MacroCard label="Protein range" macro={data.protein} />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs text-slate-400">Saved unchanged</p>
              <p className="mt-0.5 text-lg font-semibold">{data.accepted_unchanged}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">You corrected</p>
              <p className="mt-0.5 text-lg font-semibold">{data.corrected}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Estimates run</p>
              <p className="mt-0.5 text-lg font-semibold">{data.analyses}</p>
            </div>
          </div>

          {/* The load-bearing caveat. A high acceptance count is equally
              consistent with trusting the number and with never checking it,
              so it must never be read as a score. */}
          <p className="mt-3 text-xs text-slate-400">
            Saving an estimate unchanged tells the app nothing about whether it was right — the
            saved value <em>is</em> the estimate. Only the meals you corrected can measure the
            range, which is why they are counted separately.
          </p>

          {data.by_confidence.length > 0 && (
            <div className="mt-4 border-t border-slate-800 pt-3">
              <p className="mb-2 text-xs text-slate-400">
                Calorie range by the confidence it was shown with
              </p>
              <div className="flex flex-wrap gap-4">
                {data.by_confidence.map((bucket) => (
                  <p key={bucket.confidence} className="text-xs">
                    <span className="uppercase text-slate-400">{bucket.confidence}</span>{' '}
                    <span className="font-semibold">
                      {round(bucket.coverage_pct as number)}%
                    </span>{' '}
                    <span className="text-ink-faint">
                      ({bucket.covered}/{bucket.corrected})
                    </span>
                  </p>
                ))}
              </div>
            </div>
          )}

          <p className="mt-4 text-xs text-ink-faint">
            Counted only from meals you saved straight after an analysis, so the real figure may
            be a little higher. Editing a meal later is not reflected here. And how much you tell
            the app changes what this measures — weighed portions and a voice note narrow its
            range considerably, so these figures describe the app on the way <em>you</em> log,
            not on a bare photo.
          </p>
        </>
      )}
    </Card>
  )
}
