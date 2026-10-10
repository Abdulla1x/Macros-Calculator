import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** A quiet section (DESIGN.md: Blocks and rows): no border, no background,
 *  a hairline along the bottom, and an optional label with a value at the
 *  right, both in the small wide capitals. Boxes are for things you press. */
export default function Block({
  label,
  value,
  children,
  className,
}: {
  label?: string
  value?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('grid grid-cols-[minmax(0,1fr)] gap-2 border-b border-rule py-3.5', className)}>
      {label && (
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-field-label text-ink-2">{label}</h2>
          {value !== undefined && <span className="text-field-label text-ink-2 tabular-nums">{value}</span>}
        </div>
      )}
      {children}
    </section>
  )
}
