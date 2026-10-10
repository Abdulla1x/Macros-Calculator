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
 *  Newly lit segments light one after another (DESIGN.md Motion): when the
 *  gauge first appears they fade in, and when it grows afterwards each new one
 *  sweeps, lighting in the action colour and settling to its fill, 45ms apart.
 *  Only the growth sweeps, so opening Today is calm and logging a meal is
 *  seen. Segments going dark just go. Each lit segment is a fill laid over its
 *  track, mounted only when it lights, so its CSS animation runs once then and
 *  never again. Under reduced motion both are a short fade with no stagger
 *  (index.css). */
interface Lighting {
  sweep: boolean
  /** Its delay in the stagger, in ms. */
  turn: number
}

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
  // Whether this gauge has been on screen before this render: the first
  // drawing fades, growth after it sweeps.
  const shown = useRef(false)
  const growing = shown.current
  // Each segment's animation, fixed when it lights. Worked out afresh on every
  // render, a re-render for an unrelated reason (the settings arriving) changed
  // the class of segments already lit, and a changed animation name restarts
  // the animation: the first drawing replayed as a sweep.
  const lighting = useRef<(Lighting | undefined)[]>([])
  for (let index = 0; index < segments; index++) {
    if (index >= lit) lighting.current[index] = undefined
    else lighting.current[index] ??= {
      sweep: growing,
      turn: Math.max(0, index - from) * (growing ? 45 : 35),
    }
  }
  useEffect(() => {
    before.current = lit
    shown.current = true
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
                'absolute inset-0 [animation-delay:var(--turn)] motion-reduce:[animation-delay:0ms]',
                lighting.current[index]?.sweep ? 'animate-segment-sweep' : 'animate-segment-on',
                colours.on,
              )}
              style={{ '--turn': `${lighting.current[index]?.turn ?? 0}ms` } as CSSProperties}
            />
          )}
        </i>
      ))}
      {target && <i className={colours.plan} />}
    </span>
  )
}
