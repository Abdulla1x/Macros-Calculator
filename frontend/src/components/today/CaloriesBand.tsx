import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { calorieBalance, litSegments, type DayTotals } from '../../lib/today'
import Gauge from '@/ui/gauge'
import RollingNumber from '@/ui/rolling-number'

export interface BandTargets {
  calorie_goal: number
  protein_goal: number
  carbs_goal: number
  fat_goal: number
}

const n = (value: number) => Math.round(value).toLocaleString()

/** One number in a fixed place, with its label above (DESIGN.md: the
 *  training computer's data page). */
function Field({ label, children, meter }: { label: string; children: ReactNode; meter?: ReactNode }) {
  return (
    <div className="grid min-w-0 content-start gap-1.5 py-3 [&+&]:border-l [&+&]:border-band-rule [&+&]:pl-4">
      <span className="text-field-label text-band-ink-2">{label}</span>
      <span className="text-field-number leading-none">{children}</span>
      {meter}
    </div>
  )
}

function Unit({ children }: { children: ReactNode }) {
  return <small className="ml-1 text-[14px] font-semibold text-band-ink-2 [font-stretch:100%]">{children}</small>
}

/** The top of Today (DESIGN.md: The calories band). Calories as the one
 *  headline (UA-2), a 20-segment gauge closed by the plan-coloured target
 *  tick, then Eaten and Protein as fields; carbs and fat join them only when
 *  tracked, and are never mentioned otherwise.
 *
 *  Going over is drawn calmly: the label changes to "Kcal over", the gauge is
 *  simply full, and one plain line offers a way to spread it. No red, no
 *  motion (the No Red Rule, the Never Punish Rule). */
export default function CaloriesBand({
  day,
  eaten,
  targets,
  caption,
  trackCarbs,
  trackFat,
}: {
  day: string
  eaten: DayTotals
  targets: BandTargets
  caption?: string
  trackCarbs: boolean
  trackFat: boolean
}) {
  const { amount, over } = calorieBalance(eaten.calories, targets.calorie_goal)
  const macro = (value: number, goal: number) => (
    <Gauge
      segments={10}
      lit={litSegments(value, goal, 10)}
      tone="band"
      className="mt-1 h-1.5 max-w-[180px]"
    />
  )

  return (
    <section
      aria-label="Calories"
      className="-mx-4 grid grid-cols-[minmax(0,1fr)] gap-2.5 border-b border-band-rule bg-band px-4 pt-3.5 text-band-ink desk:mx-0 desk:px-7 desk:pt-5"
    >
      <h2 className="text-field-label text-band-ink-2">{over ? 'Kcal over' : 'Kcal left'}</h2>
      <p className="flex items-end gap-3">
        <span className="text-display-number desk:text-[132px]">
          <RollingNumber value={amount} />
        </span>
        <span className="pb-1.5 text-small text-band-ink-2">
          of <b className="font-semibold text-band-ink">{n(targets.calorie_goal)}</b>
          <br />
          target
        </span>
      </p>
      <Gauge
        segments={20}
        lit={litSegments(eaten.calories, targets.calorie_goal, 20)}
        target
        tone="band"
        className="h-3.5"
      />
      {(over || caption) && (
        <div className="grid gap-0.5 text-small text-band-ink-2">
          {over && (
            <p>
              Over is fine. The week evens out.{' '}
              <Link
                to={`/settings/goals?plan=${day}`}
                className="font-semibold text-band-ink underline underline-offset-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
              >
                Spread it
              </Link>
            </p>
          )}
          {caption && <p>{caption}</p>}
        </div>
      )}
      <div className="grid grid-cols-2 border-t border-band-rule">
        <Field label="Eaten">
          <RollingNumber value={eaten.calories} />
          <Unit>kcal</Unit>
        </Field>
        <Field label="Protein" meter={macro(eaten.protein, targets.protein_goal)}>
          <RollingNumber value={eaten.protein} />
          <Unit>/ {n(targets.protein_goal)} g</Unit>
        </Field>
      </div>
      {(trackCarbs || trackFat) && (
        <div className="-mt-2.5 grid grid-cols-2 border-t border-band-rule">
          {trackCarbs && (
            <Field label="Carbs" meter={macro(eaten.carbs, targets.carbs_goal)}>
              <RollingNumber value={eaten.carbs} />
              <Unit>/ {n(targets.carbs_goal)} g</Unit>
            </Field>
          )}
          {trackFat && (
            <Field label="Fat" meter={macro(eaten.fat, targets.fat_goal)}>
              <RollingNumber value={eaten.fat} />
              <Unit>/ {n(targets.fat_goal)} g</Unit>
            </Field>
          )}
        </div>
      )}
    </section>
  )
}
