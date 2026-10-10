import type { ReactNode } from 'react'

/** One tracker on Today (0a: one per row, full width): its icon and name,
 *  the day's figure at the right of the title, and its controls across the
 *  width beneath. A quiet block with a hairline below, like every other
 *  section on the page (DESIGN.md: Blocks and rows); only the controls inside
 *  are boxes, because only they are pressed. */
export default function Tracker({
  icon,
  title,
  value,
  children,
}: {
  icon: ReactNode
  title: string
  value?: ReactNode
  children?: ReactNode
}) {
  return (
    <section aria-label={title} className="grid grid-cols-[minmax(0,1fr)] gap-2.5 border-b border-rule py-3.5">
      <div className="flex min-h-11 items-center justify-between gap-3">
        <h2 className="flex items-center gap-2.5 font-semibold">
          <span aria-hidden="true" className="text-ink-2">
            {icon}
          </span>
          {title}
        </h2>
        {value !== undefined && <div className="flex items-center gap-2 text-right tabular-nums">{value}</div>}
      </div>
      {children}
    </section>
  )
}
