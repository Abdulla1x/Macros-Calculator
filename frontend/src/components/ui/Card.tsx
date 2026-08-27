import type { ComponentPropsWithRef, ElementType } from 'react'

/** The bordered box that holds a section of a page.
 *
 * `rounded-xl border border-slate-800 bg-slate-900 p-5` was typed out by hand at
 * 52 sites across 32 files. Nothing looked wrong; the problem was that no single
 * place decided what a card is, so changing one meant 52 edits and a hope that
 * none were missed -- and the copies had already begun to disagree.
 *
 * WHY `as` EXISTS, since it looks like decoration and is not. The 52 sites are
 * five different elements: ~20 <section>, ~14 <div>, 4 <p> notices and 4 auth
 * <form>s. A Card that always rendered a <div> would silently change the tag at
 * 22 of them, which is a real accessibility regression on the <section>s and
 * would break the <form>s outright. It also has to render exactly ONE element
 * and add no wrapper: twelve page roots are `space-y-6`, which compiles to
 * `> * + *`, so a wrapper between the root and a section silently eats that
 * section's top margin -- invisible to tsc, lint and build.
 *
 * The tone/pad values below are what the tree already used, not a redesign.
 * `rounded-card`, `border-line` and `bg-surface` resolve to the same three
 * values as the `rounded-xl`/`slate-800`/`slate-900` they replace, which is why
 * this migration moves no pixels.
 *
 * `danger` and `error` are both red and are deliberately NOT merged. They are
 * two spellings the app already had -- a section that is dangerous to use
 * (Danger zone) versus a message saying something failed -- and folding them
 * together would move pixels in a phase whose whole claim is that it does not.
 * Worth revisiting on purpose, not as a side effect of a refactor.
 *
 * `className` is appended last so a call site can still win.
 *
 * ComponentPropsWithRef, not ...WithoutRef: ShareCodePanel scrolls its own card
 * into view and selects the textarea inside it, so it passes a ref. React 19
 * makes ref an ordinary prop on a function component, so it rides through the
 * spread with no forwardRef. */
type CardTag = 'div' | 'section' | 'p' | 'form'

export type CardTone = 'default' | 'sunken' | 'danger' | 'warn' | 'error' | 'brand'
export type CardPad = 'none' | 'sm' | 'md' | 'lg'

// `satisfies` rather than a type annotation: it still checks that every variant
// has an entry, but keeps the literal types, so a missing key is a compile error
// instead of an `undefined` that renders an unstyled box.
const toneClass = {
  default: 'border-line bg-surface',
  sunken: 'border-line bg-slate-950/40',
  danger: 'border-rose-900/60 bg-surface',
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  error: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  brand: 'border-emerald-500/40 bg-emerald-500/5',
} satisfies Record<CardTone, string>

const padClass = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
} satisfies Record<CardPad, string>

type CardProps<T extends CardTag> = {
  as?: T
  tone?: CardTone
  pad?: CardPad
  className?: string
} & Omit<ComponentPropsWithRef<T>, 'className'>

export default function Card<T extends CardTag = 'div'>({
  as,
  tone = 'default',
  pad = 'md',
  className = '',
  ...rest
}: CardProps<T>) {
  const Tag = (as ?? 'div') as ElementType
  const classes = ['rounded-card border', toneClass[tone], padClass[pad], className]
    .filter(Boolean)
    .join(' ')
  return <Tag className={classes} {...rest} />
}
