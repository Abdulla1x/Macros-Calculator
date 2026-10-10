import type { ReactNode } from 'react'

/** One tracker on Today (0a: one per row, full width): its icon and name,
 *  the day's figure at the right of the title, and its controls across the
 *  width beneath. A quiet block with a hairline below, like every other
 *  section on the page (DESIGN.md: Blocks and rows); only the controls inside
 *  are boxes, because only they are pressed.
 *
 *  The name is set in the section label, like KCAL LEFT, EATEN and MEALS, with
 *  its icon at 18 px. It used to be body-size bold, a second heading style on
 *  one page, and the owner found the page blurred together on the P40 (he
 *  picked this over four alternatives in a prototype). */
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
        <h2 className="flex items-center gap-2 text-field-label text-ink-2">
          <span aria-hidden="true" className="[&>svg]:size-[18px]">
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
