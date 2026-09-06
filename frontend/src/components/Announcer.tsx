import { useLiveMessageState } from '../hooks/useLiveMessage'

/** The app's single live region. Mounted once, in App, above the router.
 *
 * TWO regions, not one, and they alternate. A screen reader announces a live
 * region when its content changes; writing the same string into the same region
 * twice is not a change, so a second identical failure would be silent. The
 * nonce decides which region holds the text, so consecutive announcements always
 * land in a region that was empty a moment ago.
 *
 * Both are `sr-only`, which is absolutely positioned at 1x1 with everything
 * clipped -- so this pair is out of flow and adds no space anywhere, which is
 * the property that let the region be hoisted here in the first place. See
 * hooks/useLiveMessage.ts for why it is not a role="alert" at each message.
 *
 * `polite` rather than `assertive` throughout: these report the outcome of
 * something the user just did, and none of them is urgent enough to cut off a
 * sentence already being read. */
export default function Announcer() {
  const { text, nonce } = useLiveMessageState()
  const useFirst = nonce % 2 === 0

  return (
    <>
      <div role="status" aria-live="polite" className="sr-only">
        {useFirst ? text : ''}
      </div>
      <div role="status" aria-live="polite" className="sr-only">
        {useFirst ? '' : text}
      </div>
    </>
  )
}
