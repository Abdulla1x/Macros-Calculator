import { useEffect, useRef, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

const TONES = {
  // On the page's own ground: water, the unlock meters.
  ground: { on: 'bg-fill', off: 'bg-track', plan: 'bg-plan' },
  // Inside the calories band, which has its own colours in every palette but
  // Daylight (DESIGN.md: The calories band).
  band: { on: 'bg-band-fill', off: 'bg-band-track', plan: 'bg-band-plan' },
} as const

/** A segmented gauge (DESIGN.md: Gauges and meters). Square segments, lit in
 *  ink and unlit in track, never a ring. With `target`, a thin plan-coloured
 *  tick closes the row: the goal the segments fill towards.
 *
 *  Decorative to assistive technology: the number beside a gauge says the
 *  same thing in words, and twenty unnamed boxes would only be noise. Callers
 *  set the height.
 *
 *  Newly lit segments light one after another (DESIGN.md Motion: 220ms each,
 *  35ms apart); segments going dark just go. Each lit segment is a fill laid
 *  over its track, mounted only when it lights, so its CSS animation runs once
 *  then and never again. Under reduced motion it is a short fade with no
 *  stagger (index.css). */
export default function Gauge({
  segments,
  lit,
  target = false,
  tone = 'ground',
  className,
}: {
  segments: number
  lit: number
  target?: boolean
  tone?: keyof typeof TONES
  className?: string
}) {
  const colours = TONES[tone]
  // How many were lit on the previous render: the ones beyond it are new.
  const before = useRef(0)
  const from = Math.min(before.current, lit)
  useEffect(() => {
    before.current = lit
  }, [lit])
  return (
    <span
      aria-hidden="true"
      data-gauge=""
      className={cn('grid gap-[3px]', className)}
      style={{
        gridTemplateColumns: `repeat(${segments}, minmax(0, 1fr))${target ? ' 3px' : ''}`,
      }}
    >
      {Array.from({ length: segments }, (_, index) => (
        <i key={index} data-lit={index < lit ? '' : undefined} className={cn('relative', colours.off)}>
          {index < lit && (
            <b
              className={cn(
                'absolute inset-0 animate-segment-on [animation-delay:var(--turn)] motion-reduce:[animation-delay:0ms]',
                colours.on,
              )}
              style={{ '--turn': `${Math.max(0, index - from) * 35}ms` } as CSSProperties}
            />
          )}
        </i>
      ))}
      {target && <i className={colours.plan} />}
    </span>
  )
}
