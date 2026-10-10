import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { NextIcon } from '@/ui/icons'

/** A row that opens something (DESIGN.md: Blocks and rows): at least 52px
 *  tall, a label with optional detail beneath, and a chevron. As a link or a
 *  button, styled the same. */
const ROW =
  'flex min-h-[52px] w-full items-center gap-3 py-2 text-left text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action disabled:pointer-events-none disabled:opacity-45'

function Content({ icon, label, detail, chevron }: { icon?: ReactNode; label: ReactNode; detail?: ReactNode; chevron: boolean }) {
  return (
    <>
      {icon && <span className="shrink-0 text-ink-2">{icon}</span>}
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="font-semibold">{label}</span>
        {detail && <span className="text-small text-ink-2">{detail}</span>}
      </span>
      {chevron && <NextIcon size={18} aria-hidden="true" className="shrink-0 text-ink-2" />}
    </>
  )
}

export function RowLink({
  to,
  icon,
  label,
  detail,
  className,
}: {
  to: string
  icon?: ReactNode
  label: ReactNode
  detail?: ReactNode
  className?: string
}) {
  return (
    <Link to={to} className={cn(ROW, className)}>
      <Content icon={icon} label={label} detail={detail} chevron />
    </Link>
  )
}

export function RowButton({
  icon,
  label,
  detail,
  chevron = false,
  className,
  ...props
}: Omit<ComponentProps<'button'>, 'children'> & {
  icon?: ReactNode
  label: ReactNode
  detail?: ReactNode
  chevron?: boolean
}) {
  return (
    <button type="button" className={cn(ROW, className)} {...props}>
      <Content icon={icon} label={label} detail={detail} chevron={chevron} />
    </button>
  )
}
