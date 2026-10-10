import { useId, useState, type ReactNode } from 'react'
import { ExpandIcon } from '@/ui/icons'
import { cn } from '@/lib/utils'

/** "How is this worked out?": the reasoning behind a number, one tap away
 *  instead of always on screen (UA-9's rule: one sentence inline, the rest
 *  behind a disclosure). Closed by default, every time; nothing remembers it,
 *  because the text is reference, not a preference.
 *
 *  A real button with aria-expanded, so a screen reader hears "collapsed" or
 *  "expanded", and the text is in the DOM only while open. */
export default function Explainer({
  label = 'How is this worked out?',
  children,
  className,
}: {
  label?: string
  children: ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className={cn('grid justify-items-start gap-1', className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((now) => !now)}
        className="inline-flex min-h-8 items-center gap-1 text-small text-ink-2 underline underline-offset-3 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        {label}
        <ExpandIcon size={14} aria-hidden="true" className={open ? 'rotate-180' : undefined} />
      </button>
      <div id={id} hidden={!open} className="text-small text-ink-2">
        {open && children}
      </div>
    </div>
  )
}
