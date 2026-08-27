import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { BodyTargets } from '../../types'
import Card from '../ui/Card'

// Field name → what to ask the user for. Keyed on what the API returns so a
// field added server-side without a label here still shows *something*.
const missingLabels: Record<string, string> = {
  weight: 'a recent weigh-in',
  height_cm: 'your height',
  birth_date: 'your date of birth',
  sex: 'your sex',
  activity_level: 'your activity level',
  goal_rate_kg_per_week: 'a goal rate',
}

/** The derived numbers, each next to what it was computed from.
 *
 * None of these are measurements of the person, and the card should not let
 * them look like one — same principle as TrendReadout on the Weight page. The
 * weight and the date it was logged are shown because body weight is the input
 * most likely to be quietly out of date. */
export default function BodyTargetsCard({
  reloadKey,
  unit,
}: {
  reloadKey: number
  unit: 'kg' | 'lb'
}) {
  const [targets, setTargets] = useState<BodyTargets | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getBodyTargets()
      .then((next) => {
        if (!cancelled) {
          setTargets(next)
          setFailed(false)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  if (failed) return null
  if (!targets) {
    return (
      <Card as="section">
        <h2 className="mb-1 font-semibold">What your profile works out to</h2>
        <p className="text-sm text-slate-400">Loading…</p>
      </Card>
    )
  }

  const stillNeeded = targets.missing
    .map((field) => missingLabels[field] ?? field)
    .join(', ')

  const measured = targets.tdee_source === 'measured'
  const basis = targets.tdee_basis

  const rows: { label: string; value: string; caption: string }[] = [
    {
      label: 'BMI',
      value: targets.bmi === null ? '—' : targets.bmi.toFixed(1),
      caption: 'Your weight against your height. Says nothing about body composition.',
    },
    {
      label: 'Resting burn (BMR)',
      value: targets.bmr === null ? '—' : `${Math.round(targets.bmr)} kcal`,
      caption: 'Mifflin-St Jeor, from your height, weight, age and sex.',
    },
    {
      label: measured ? 'Daily burn (measured)' : 'Daily burn (estimated)',
      value: targets.tdee === null ? '—' : `${Math.round(targets.tdee)} kcal`,
      caption: measured
        ? `Measured from what you actually logged: ${basis?.logged_days} days of meals against ${basis?.weigh_ins} weigh-ins over ${basis?.span_days} days. The formula would have said ${Math.round(targets.tdee_estimated ?? 0)} kcal.`
        : 'Resting burn × a fixed multiplier for your activity level. The multiplier is a convention, and the roughest step here.',
    },
    {
      label: 'Calorie target',
      value:
        targets.target_calories === null
          ? '—'
          : `${Math.round(targets.target_calories)} kcal`,
      caption: measured
        ? 'Your measured daily burn, adjusted for the rate you asked for.'
        : 'Your daily burn, adjusted for the rate you asked for.',
    },
    {
      label: 'Macro split',
      value:
        targets.protein_g === null
          ? '—'
          : `${targets.protein_g} P · ${targets.carbs_g} C · ${targets.fat_g} F`,
      caption:
        'Protein from your body weight, fat as a quarter of calories, carbs the remainder.',
    },
    {
      label: 'Weight used',
      value:
        targets.weight_kg === null
          ? '—'
          : `${targets.weight_kg.toFixed(1)} kg`,
      caption:
        targets.weight_date === null
          ? 'No weigh-in in the last 90 days, so nothing here can be calculated.'
          : `Your smoothed trend weight as of ${targets.weight_date}.`,
    },
  ]

  return (
    <Card as="section">
      <h2 className="mb-1 font-semibold">What your profile works out to</h2>
      <p className="mb-4 text-sm text-slate-400">
        {measured
          ? 'Your daily burn is now measured from your own logs — what you ate, ' +
            'against how your weight actually moved — rather than predicted by a ' +
            'formula. BMI and resting burn below are still formulas.'
          : 'Estimates, not measurements — a formula applied to what you typed above. ' +
            'They can be a few hundred calories out for any one person, so treat them ' +
            'as a starting point and let your own weight trend correct them.'}
        {unit === 'lb' && ' Weights here are shown in kg, as the formulas use them.'}
      </p>

      {stillNeeded && (
        <p className="mb-4 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-300">
          Add {stillNeeded} to see the rest.
        </p>
      )}

      {!measured && basis?.unavailable_reason && (
        <p className="mb-4 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-300">
          {basis.unavailable_reason}
        </p>
      )}

      {targets.clamped_reason && (
        <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          {targets.clamped_reason}
        </p>
      )}

      <dl className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label}>
            <dt className="text-xs text-slate-400">{row.label}</dt>
            <dd className="text-lg font-semibold">{row.value}</dd>
            <p className="mt-0.5 text-xs text-ink-faint">{row.caption}</p>
          </div>
        ))}
      </dl>
    </Card>
  )
}
