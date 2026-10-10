import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** DESIGN.md (Components -> Chips): 36px tall, a 1.5px rule border, 5px
 *  radius; selected is an ink fill with ground-coloured text. A toggle when
 *  `pressed` is given (aria-pressed), a plain button otherwise. */
export function Chip({ pressed, className, ...props }: ComponentProps<'button'> & { pressed?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={cn(
        'inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-control border-[1.5px] px-3 text-[13.5px] font-semibold whitespace-nowrap',
        'transition-[background-color,border-color,color] duration-150 ease-out-expo',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action',
        pressed ? 'border-ink bg-ink text-ground' : 'border-rule text-ink hover:border-ink',
        className,
      )}
      {...props}
    />
  )
}
