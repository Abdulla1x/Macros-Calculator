/** DESIGN.md's motion tokens, for code that animates with Motion.
 *
 *  CSS transitions use the same ease through index.css (`ease-out-expo`).
 *  Durations are in seconds, which is what Motion takes.
 *
 *  ⚠ Always end a transform on an explicit value -- `scale: 1`, `y: 0` --
 *  never `transform: 'none'`. Motion read a 'none' end state as scale 0 in the
 *  prototype and made gauge segments, bars and tags vanish (DESIGN.md). */

/** The default ease: an exponential ease-out. */
export const EASE = [0.16, 1, 0.3, 1] as const
/** Closing the Log panel: an ease-in, so it leaves rather than lands. */
export const EASE_IN = [0.4, 0, 1, 1] as const

export const DURATION = {
  /** Tab changes: a crossfade. */
  fast: 0.15,
  /** Most transitions. */
  base: 0.24,
  /** Pushing a screen, and going back. */
  screen: 0.26,
  /** Under reduced motion, only fades remain, at this length. */
  reduced: 0.12,
} as const

/** A pushed screen slides this far (px), from the right on push and from the
 *  left on back. */
export const SCREEN_SHIFT = 28

export const SPRING = {
  /** The Log panel opening. */
  panel: { type: 'spring', stiffness: 380, damping: 36 },
  /** A toast rising 18px into place. */
  toast: { type: 'spring', stiffness: 420, damping: 32 },
} as const

/** Motion's DOM animation features, loaded on demand by LazyMotion (App.tsx),
 *  so they stay out of the first download. */
export const loadMotionFeatures = () => import('./motionFeatures').then((module) => module.default)
