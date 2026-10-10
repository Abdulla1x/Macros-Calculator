import type { ReactNode } from 'react'
import { litSegments } from '../lib/today'
import Explainer from '@/ui/explainer'
import Gauge from '@/ui/gauge'
import RollingNumber from '@/ui/rolling-number'
import Tracker from './today/Tracker'

/**
 * The shell every daily quick-log tracker renders inside.
 *
 * What they share is the frame: a label, a value against a goal, a meter,
 * somewhere to explain where the goal came from, and somewhere to put the
 * controls. What they do NOT share is the controls themselves -- water adds
 * fixed amounts, steps sets one number for the day, supplements ticks items off
 * a list -- so `actions` is a slot, not a prop shape guessed at in advance.
 *
 * Built on Today's Tracker block (one per row, a hairline below) with a
 * 10-segment meter (DESIGN.md: Gauges and meters; never a ring, never a
 * percentage beside a checklist, UA-12).
 */
interface Props {
  icon: ReactNode
  label: string
  value: number
  /** Null when the tracker has no goal to measure against, which is a state
   *  and not a gap: steps has no honest derivation for one, so until the user
   *  sets it the card shows the count and drops the bar rather than drawing
   *  progress towards a number nobody chose. */
  goal: number | null
  unit: string
  /** The figure at the right of the title, when "value / goal unit" is not
   *  the right way to say it ("2 of 3", "All done"). */
  valueText?: ReactNode
  /** False for a tracker whose progress is a list, already visible below. */
  meter?: boolean
  /** A status line, always shown, small ("Next at 21:00"). */
  caption?: ReactNode
  /** Where the goal or a figure came from, behind "How is this worked out?"
   *  (after a phone test: always-on explanations made the cards read as a
   *  wall of text). */
  explanation?: ReactNode
  actions?: ReactNode
  error?: string | null
}

export default function DailyTrackerCard({
  icon,
  label,
  value,
  goal,
  unit,
  valueText,
  meter = true,
  caption,
  explanation,
  actions,
  error,
}: Props) {
  const hasGoal = goal !== null && goal > 0
  const n = (amount: number) => Math.round(amount).toLocaleString()

  return (
    <Tracker
      icon={icon}
      title={label}
      value={
        valueText ?? (
          <span>
            {/* Rolls like the calories figure (picked after a phone
                test found water and steps "static or sudden"). */}
            <span className="font-semibold">
              <RollingNumber value={value} />
            </span>
            <span className="text-ink-2">
              {hasGoal && ` / ${n(goal!)}`} {unit}
            </span>
          </span>
        )
      }
    >
      {/* Goal-relative, so with no goal it has nothing to say. An empty track
          would read as failure rather than as a setting nobody filled in. */}
      {meter && hasGoal && (
        <div
          role="progressbar"
          aria-valuenow={Math.round(value)}
          aria-valuemin={0}
          aria-valuemax={Math.round(goal!)}
          aria-label={`${label}: ${n(value)} of ${n(goal!)} ${unit}`}
        >
          <Gauge segments={10} lit={litSegments(value, goal!, 10)} className="h-2.5" />
        </div>
      )}

      {actions}

      {error && (
        <p role="alert" className="border-l-2 border-ink pl-3 text-small">
          {error}
        </p>
      )}

      {caption && <p className="text-small text-ink-2">{caption}</p>}
      {explanation && <Explainer>{explanation}</Explainer>}
    </Tracker>
  )
}
