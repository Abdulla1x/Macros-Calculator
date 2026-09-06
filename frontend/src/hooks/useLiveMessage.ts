import { useEffect, useSyncExternalStore } from 'react'

/** One live region for the whole app, and the hook that speaks into it.
 *
 * WHY THERE IS A STORE HERE RATHER THAN A role="alert" AT EACH SITE. The app
 * renders ~46 status messages as `{error && <p>…</p>}` -- they come into
 * existence at the moment they have something to say. Phase 15 measured what
 * that does: StatusBanner returned null until its text arrived, and because the
 * live region was not in the document beforehand, it was never announced. The
 * fix there was to render the wrapper unconditionally. Doing that at 46 sites is
 * not the same cheap change, because an always-present empty wrapper is not
 * inert: twelve page roots are `space-y-6`, which compiles to `> * + *`, and
 * several message sites sit in `gap-*` flex rows. An empty div in either adds a
 * gap that tsc, lint and the build all consider correct.
 *
 * So the region lives once, at the root, in Announcer -- where nothing spaces
 * its children and `sr-only` takes it out of flow entirely -- and every site
 * pushes text to it instead. The visible <p> does not move and does not change.
 *
 * ⚠ NOT NAMED useAnnounce, THOUGH THAT READS BETTER. hooks/useAnnouncements.ts
 * already exists and fetches the release notes -- a completely unrelated thing
 * that happens to share the English word. Two hooks one letter apart in the same
 * directory is a mis-import waiting to happen, and it already happened once:
 * a check for whether this import was present matched the OTHER hook's path as a
 * substring and silently skipped four files.
 *
 * ⚠ THE nonce IS NOT DECORATION. A live region announces when its CONTENT
 * CHANGES. Saving twice and failing the same way twice writes the same string,
 * the text node does not change, and the second failure is silent -- which is
 * exactly the case where a user most needs telling. The nonce increments on
 * every announcement and Announcer alternates which of its two regions holds the
 * text, so the content genuinely changes even when the message does not. */
export type Announcement = { text: string; nonce: number }

let current: Announcement = { text: '', nonce: 0 }
const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

// Returns the same object identity until something is announced, which is what
// useSyncExternalStore requires -- a snapshot that is a fresh object every call
// re-renders forever.
const getSnapshot = () => current

/** For Announcer. Nothing else should need it. */
export function useLiveMessageState(): Announcement {
  return useSyncExternalStore(subscribe, getSnapshot)
}

/** Announce `text` whenever it becomes non-empty.
 *
 * Written to be a one-line addition at a call site that already has the string
 * in a variable: `useLiveMessage(error)`. Empty, null and undefined say nothing, so
 * the common `const [error, setError] = useState('')` needs no guard, and
 * clearing an error does not announce silence. */
export function useLiveMessage(text: string | null | undefined): void {
  useEffect(() => {
    if (!text) return
    current = { text, nonce: current.nonce + 1 }
    for (const listener of listeners) listener()
  }, [text])
}
