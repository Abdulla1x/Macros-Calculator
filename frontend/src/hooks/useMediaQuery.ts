import { useCallback, useSyncExternalStore } from 'react'

/** Whether a media query matches, kept in step as the window changes.
 *
 *  For the few decisions CSS cannot make on its own, such as which edge the
 *  Log panel slides in from: a Motion animation takes its start position in
 *  JavaScript, so a `desk:` class cannot pick it. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches)
}
