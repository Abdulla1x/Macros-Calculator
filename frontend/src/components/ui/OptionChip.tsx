import type { ComponentPropsWithRef } from 'react'

/** A bordered pill wrapping a radio or checkbox and its text.
 *
 * These four sites carry the *input* class string -- rounded-lg, the slate-700
 * border, the slate-800 ground -- but they are <label> elements, not inputs. A
 * find-and-replace of that string onto ui/TextInput wrecks them, which is why
 * they get their own primitive rather than being swept up.
 *
 * The chip is the hit target, not the box inside it: it wraps its own input, so
 * the whole pill is clickable and no htmlFor/id pair is needed. That is the
 * convention across this app -- 45 labels, two htmlFor -- and the reason this
 * takes children rather than a `label` string.
 *
 * `block` is the one real variant: a full-width row whose text wraps under a
 * top-aligned box, used where the explanation runs to several lines
 * ("Work out my goals from my body profile"). The default is the inline pill
 * that sits in a flex-wrap row beside its siblings. */
export default function OptionChip({
  block = false,
  className = '',
  children,
  ...rest
}: {
  block?: boolean
} & ComponentPropsWithRef<'label'>) {
  const classes = [
    'flex cursor-pointer rounded-control border border-line-strong bg-raised text-sm',
    block ? 'items-start gap-3 px-4 py-3' : 'items-center gap-2 px-4 py-2',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <label className={classes} {...rest}>
      {children}
    </label>
  )
}
