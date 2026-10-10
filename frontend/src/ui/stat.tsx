import type { ReactNode } from 'react'

/** A number in a fixed field, its label above (DESIGN.md: "put every number in
 *  a field with a label above it"). Laid side by side in a StatGrid, with a
 *  hairline between neighbours. */
export function Stat({ label, children, unit }: { label: string; children: ReactNode; unit?: ReactNode }) {
  return (
    <div className="grid min-w-0 content-start gap-1.5 py-2.5">
      <span className="text-field-label text-ink-2">{label}</span>
      <span className="text-field-number leading-none">
        {children}
        {unit && <small className="ml-1 text-[14px] font-semibold text-ink-2 [font-stretch:100%]">{unit}</small>}
      </span>
    </div>
  )
}

export function StatGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 [&>*:nth-child(even)]:border-l [&>*:nth-child(even)]:border-rule [&>*:nth-child(even)]:pl-4 [&>*:nth-child(n+3)]:border-t [&>*:nth-child(n+3)]:border-rule">
      {children}
    </div>
  )
}
