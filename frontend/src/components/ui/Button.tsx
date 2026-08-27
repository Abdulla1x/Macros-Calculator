import type { ComponentPropsWithRef } from 'react'

/** The app's primary and destructive buttons.
 *
 * Primary was spelled two ways -- `bg-emerald-500` + `text-slate-950` at 13
 * sites and `bg-brand` + `text-brand-ink` at 4 -- which render identically
 * because the tokens resolve to exactly those two hexes. That is the most
 * dangerous kind of duplication: retuning the brand would have moved 4 of 17
 * buttons and left the other 13 behind.
 *
 * WHY THERE IS NO `size` PROP, which the amendment expected. Measured across
 * the 17 primary sites, the padding is px-5 py-2 x9, px-4 py-2 x3,
 * px-3 py-1.5 x2, and then px-6 py-2.5, px-5 py-2.5 and px-4 py-1.5 once each.
 * Six spellings for seventeen buttons is not a scale, and a `size` prop would
 * either need six meaningless names or would move pixels at the outliers.
 * Geometry stays at the call site; what repeats -- colour, weight, radius,
 * hover and disabled -- is what moved in here. Two competing px-* utilities
 * would resolve by stylesheet order rather than class order, so this is a real
 * constraint and not a preference.
 *
 * WHY THERE IS NO `secondary` VARIANT. The bordered ghost buttons look like one
 * family and are not: ~20 sites disagreeing on padding, text size, text colour
 * and hover treatment (hover:border-emerald-500 versus hover:bg-slate-800).
 * They are one-offs, and the amendment's own rule for this phase is to
 * enumerate rather than sweep.
 *
 * danger keeps text-white deliberately. Phase 15 measured bg-rose-600 with
 * text-white at 4.70:1 and checked the obvious "fix": text-slate-950 drops it
 * to 4.29 and fails AA. */
export type ButtonVariant = 'primary' | 'danger'

const variantClass = {
  primary: 'bg-brand text-brand-ink hover:bg-emerald-400 disabled:opacity-60',
  danger: 'bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-60',
} satisfies Record<ButtonVariant, string>

const base = 'rounded-control text-sm font-semibold'

/** For the two <Link>s that are styled as primary buttons.
 *
 * They stay links rather than becoming `<Button as={Link}>`: they navigate, so
 * they have to render an <a>, and saying that at the call site is clearer than
 * a polymorphic prop threaded through for two callers. Same escape hatch as
 * inputSurfaceClass in ui/TextInput. */
export const primaryButtonClass = `${base} ${variantClass.primary}`

export default function Button({
  variant = 'primary',
  className = '',
  ...rest
}: {
  variant?: ButtonVariant
} & Omit<ComponentPropsWithRef<'button'>, 'className'> & { className?: string }) {
  return <button className={[base, variantClass[variant], className].filter(Boolean).join(' ')} {...rest} />
}
