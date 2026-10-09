import type { ComponentProps } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { Slot } from 'radix-ui'
import { cn } from '@/lib/utils'

/** shadcn/ui's Button, re-themed to DESIGN.md (Components -> Buttons).
 *
 *  The structure is shadcn's: cva variants, `asChild` to render a link with a
 *  button's look, `data-slot` for styling from a parent. Every style is
 *  replaced -- shadcn's default look is a recognisable generic one and is
 *  never shipped (decision 1 of the revamp).
 *
 *  - Flat: no shadows (the Flat Rule); depth is tone.
 *  - The action colour only on things you press (the Press Rule): `primary`.
 *  - 42px tall, 44px for an icon button; the Log button 50px.
 *  - Transitions name their properties; `transition-all` is a Web Interface
 *    Guidelines anti-pattern (UA-16) and would animate layout too. */
const buttonVariants = cva(
  [
    'inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap select-none',
    'rounded-control border-[1.5px] font-semibold text-[14.5px] [font-stretch:105%]',
    'transition-[background-color,border-color,color,opacity] duration-150 ease-out-expo',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action',
    'disabled:pointer-events-none disabled:opacity-45',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0',
  ],
  {
    variants: {
      variant: {
        primary: 'border-action bg-action text-action-ink hover:bg-action/90',
        secondary: 'border-ink bg-transparent text-ink hover:bg-ink/5',
        ghost: 'border-rule bg-transparent text-ink hover:bg-ink/5',
        // The middle of the tab bar and the top of the side rail.
        log: 'gap-2 rounded-log border-ink bg-ink text-[15px] font-bold text-ground [font-stretch:108%] tracking-[0.02em] hover:bg-ink/90',
      },
      size: {
        default: 'h-[42px] px-4',
        log: 'h-[50px] px-5',
        icon: 'size-11',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'default',
    },
  },
)

function Button({
  className,
  variant = 'primary',
  size = 'default',
  asChild = false,
  ...props
}: ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    /** Render the single child (a router Link, say) with a button's look. */
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : 'button'
  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

// eslint-disable-next-line react/only-export-components -- shadcn's shape: the variants are shared with links styled as buttons.
export { Button, buttonVariants }
