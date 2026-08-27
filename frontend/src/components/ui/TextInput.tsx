import type { ComponentPropsWithRef, ElementType } from 'react'

/** Anything you type in: <input>, and via `as` the one <select> and the one
 *  <textarea> that wear the same clothes.
 *
 * `border-slate-700 bg-slate-800 …` was typed out at 20 real input sites plus
 * four hoisted consts that each existed because someone had already noticed the
 * duplication inside one file. rounded-control, border-line-strong and bg-raised
 * resolve to the same three values as the rounded-lg/slate-700/slate-800 they
 * replace, so nothing moves.
 *
 * `size` is not a style preference, it is the mobile-zoom guard, and the two
 * values are both already in the tree:
 *
 *   'sm'  text-base sm:text-sm -- 16px on a phone, 14px from sm up. Anything
 *         under 16px makes mobile Safari and Chrome zoom the viewport on focus,
 *         and there is no touch keyboard above the breakpoint to trigger it.
 *         Phase 15 measured 34 fields under 16px and fixed 28 reachable ones.
 *   'md'  text-base -- 16px at every width. The auth pages, which carry two or
 *         three fields and no dense layout to fit them into. They set no font
 *         class at all today and inherit 16px from body, so naming it changes
 *         nothing on screen; shrinking them to match 'sm' would.
 *
 * `accent` formalises a system that already existed rather than flattening it:
 * Water and Steps carry a per-tracker focus hue matching the `color` props on
 * WaterCard and StepsCard, which read trackerHues from lib/chartTheme.ts.
 * Note the focus borders are the 500 shades while trackerHues are the 400s --
 * a deliberate step deeper for a 3:1 non-text target, and the reason these stay
 * literals rather than pointing at --color-water / --color-steps.
 *
 * placeholder-ink-muted is in the base, not per-site. index.css already states
 * the rule -- ink-muted rather than ink-faint on --color-raised, 5.71:1 -- and
 * the two HeightField placeholders were the only ones left on the browser
 * default, which is the lower-contrast option. */
type InputTag = 'input' | 'select' | 'textarea'

export type InputAccent = 'brand' | 'water' | 'steps'
export type InputSize = 'sm' | 'md'
export type InputPad = 'sm' | 'md'

/** The input's own border and ground, without the interactive parts.
 *
 * FoodAutocomplete's suggestion list is a floating panel that deliberately wears
 * this so it reads as that input's own drawer rather than as a separate card.
 * Exported as a const, which oxlint's allowConstantExport permits beside a
 * component; a function here would warn. */
export const inputSurfaceClass = 'rounded-control border border-line-strong bg-raised'

const accentClass = {
  brand: 'focus:border-brand',
  water: 'focus:border-sky-500',
  steps: 'focus:border-violet-500',
} satisfies Record<InputAccent, string>

const sizeClass = {
  sm: 'text-base sm:text-sm',
  md: 'text-base',
} satisfies Record<InputSize, string>

const padClass = {
  sm: 'px-2 py-1.5',
  md: 'px-3 py-2',
} satisfies Record<InputPad, string>

type TextInputProps<T extends InputTag> = {
  as?: T
  accent?: InputAccent
  size?: InputSize
  pad?: InputPad
  className?: string
} & Omit<ComponentPropsWithRef<T>, 'className' | 'size'>

export default function TextInput<T extends InputTag = 'input'>({
  as,
  accent = 'brand',
  size = 'sm',
  pad = 'md',
  className = '',
  ...rest
}: TextInputProps<T>) {
  const Tag = (as ?? 'input') as ElementType
  const classes = [
    inputSurfaceClass,
    padClass[pad],
    sizeClass[size],
    'placeholder-ink-muted',
    accentClass[accent],
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <Tag className={classes} {...rest} />
}
