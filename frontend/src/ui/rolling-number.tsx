import { useState, type CSSProperties } from 'react'
import { changedDigits } from '../lib/today'

interface Shown {
  value: number
  text: string
  /** One key per character. A character's key changes only when it does,
   *  so React remounts exactly the changed ones and their animation runs. */
  keys: string[]
  turns: (number | null)[]
  direction: 'up' | 'down'
  /** Hands out fresh keys; only ever grows. */
  next: number
}

function first(value: number, text: string): Shown {
  return { value, text, keys: [...text].map((_, i) => `s${i}`), turns: [], direction: 'up', next: 0 }
}

/** A number whose changed digits roll into place (DESIGN.md Motion: 0.45em,
 *  320ms, 40ms apart from the right; up when the value rises, down when it
 *  falls). Plain CSS, like the route fade: Today is the first screen, and it
 *  should not wait for the animation library to download before it moves.
 *  Under reduced motion the number simply changes (index.css).
 *
 *  Screen readers get the number once, whole; the per-digit spans are hidden
 *  from them so nothing reads it out a digit at a time. */
export default function RollingNumber({ value }: { value: number }) {
  const text = Math.round(value).toLocaleString()
  const [shown, setShown] = useState(() => first(value, text))

  // Adjusting state while rendering, React's pattern for state derived from a
  // prop: the change is seen in the same render that receives it.
  if (shown.text !== text) {
    const turns = changedDigits(shown.text, text)
    // Right-aligned, like the comparison: keep the key of every character
    // that stayed, mint one for every character that changed.
    const offset = shown.text.length - text.length
    let next = shown.next
    const keys = [...text].map((_, i) =>
      turns[i] === null ? (shown.keys[i + offset] ?? `n${next++}`) : `n${next++}`,
    )
    setShown({ value, text, keys, turns, direction: value >= shown.value ? 'up' : 'down', next })
  }

  return (
    <>
      <span aria-hidden="true" className="inline-flex">
        {[...shown.text].map((char, i) => {
          const turn = shown.turns[i]
          return turn === null || turn === undefined ? (
            <span key={shown.keys[i]}>{char}</span>
          ) : (
            <span
              key={shown.keys[i]}
              className={`inline-block ${
                shown.direction === 'up' ? 'animate-roll-up' : 'animate-roll-down'
              } [animation-delay:var(--turn)]`}
              style={{ '--turn': `${turn * 40}ms` } as CSSProperties}
            >
              {char}
            </span>
          )
        })}
      </span>
      <span className="sr-only">{text}</span>
    </>
  )
}
