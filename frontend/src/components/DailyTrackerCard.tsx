import type { ReactNode } from 'react'
import Card from './ui/Card'

/**
 * The shell every daily quick-log tracker renders inside.
 *
 * Water is the first one; steps and supplements are meant to be the second and
 * third, which is why this is a shell with slots rather than a water card with
 * generic-sounding prop names. What they share is the frame: a label, a
 * value against a goal, a bar, somewhere to explain where the goal came from,
 * and somewhere to put the controls. What they do NOT share is the controls
 * themselves — water adds fixed amounts, steps sets one number for the day,
 * supplements ticks items off a list — so `actions` is a slot, not a prop
 * shape guessed at in advance.
 *
 * A bar rather than a ring, deliberately. The rings above it on the dashboard
 * are the macro targets, and giving a secondary tracker the same visual weight
 * as the calorie ring would say something about its importance that isn't
 * true.
 */
interface Props {
  icon: string
  label: string
  value: number
  /** Null when the tracker has no goal to measure against, which is a state
   *  and not a gap: steps has no honest derivation for one, so until the user
   *  sets it the card shows the count and drops the bar rather than drawing
   *  progress towards a number nobody chose. */
  goal: number | null
  unit: string
  color: string
  /** Where the goal came from. Rendered under the bar, small. */
  caption?: ReactNode
  actions?: ReactNode
  error?: string | null
}

export default function DailyTrackerCard({
  icon,
  label,
  value,
  goal,
  unit,
  color,
  caption,
  actions,
  error,
}: Props) {
  // Capped at 1 for the bar's width so overshooting cannot overflow the
  // container, but the percentage below is uncapped: someone who drank 120% of
  // their goal should be told 120%, not a silently clipped 100%.
  const hasGoal = goal !== null && goal > 0
  const ratio = hasGoal ? value / goal! : 0
  const width = Math.min(ratio, 1) * 100

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-semibold">
          <span className="mr-2">{icon}</span>
          {label}
        </h2>
        <span className="text-sm text-slate-400">
          <span className="font-semibold text-slate-200">
            {Math.round(value).toLocaleString()}
          </span>{' '}
          {hasGoal && `/ ${Math.round(goal!).toLocaleString()} `}
          {unit}
        </span>
      </div>

      {/* Both the bar and the percentage are goal-relative, so with no goal
          they have nothing to say. Rendering them anyway would draw an empty
          track and "0% of goal" — which reads as failure rather than as a
          setting nobody has filled in. */}
      {hasGoal && (
        <>
          <div
            className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-800"
            role="progressbar"
            aria-valuenow={Math.round(value)}
            aria-valuemin={0}
            aria-valuemax={Math.round(goal!)}
            aria-label={`${label}: ${Math.round(value)} of ${Math.round(goal!)} ${unit}`}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${width}%`, background: color }}
            />
          </div>
          <p className="mt-1 text-right text-xs text-ink-faint">
            {Math.round(ratio * 100)}% of goal
          </p>
        </>
      )}

      {actions && <div className="mt-3">{actions}</div>}

      {error && (
        <p className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {caption && <p className="mt-3 text-xs text-ink-faint">{caption}</p>}
    </Card>
  )
}
