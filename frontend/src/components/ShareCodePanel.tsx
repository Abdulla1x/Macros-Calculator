import { useEffect, useRef, useState } from 'react'
import { Button } from '@/ui/button'
import { CloseIcon } from '@/ui/icons'

/** Shows a meal code and helps the user get it into a message.
 *
 * The textarea is always rendered and Copy is only a convenience. That is
 * deliberate: navigator.clipboard is *undefined* on an insecure origin — which
 * is how this app gets opened on a phone over the LAN — and throws on Safari
 * without a fresh user gesture, when the document is unfocused, or when the
 * permission is denied. Treating the button as the primary path would make all
 * of those a dead end; treating it as a shortcut over a visible, selectable
 * textarea makes them a non-event. It is also better to let someone see what
 * they are about to send.
 *
 * No document.execCommand fallback: it is deprecated, and the textarea is
 * already the better answer.
 */
export default function ShareCodePanel({
  label,
  code,
  onClose,
}: {
  label: string
  code: string
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  // The triggers are a meal row on the dashboard or a saved-meal row in
  // Settings -> Library, either of which can be well away from here. Without
  // this the panel opens off-screen and the tap reads as having done nothing.
  useEffect(() => {
    box.current?.scrollIntoView({ block: 'nearest' })
  }, [])

  const copy = async () => {
    let ok = false
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code)
        ok = true
      }
    } catch {
      // Insecure origin, denied permission, no transient activation, unfocused
      // document. They mean the same thing to the reader and the textarea above
      // is already the answer, so none of them is worth telling apart.
      ok = false
    }
    setCopied(ok)
    if (!ok) box.current?.querySelector('textarea')?.select()
  }

  return (
    <section ref={box} aria-label="Meal code" className="grid grid-cols-[minmax(0,1fr)] gap-2.5 border-y border-rule py-3.5">
      <div className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 font-semibold">Meal code for “{label}”</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the meal code"
          className="-mt-2 -mr-2 grid size-11 shrink-0 place-items-center rounded-control text-ink-2 hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
        >
          <CloseIcon size={18} />
        </button>
      </div>
      <p className="text-small text-ink-2">
        Anyone with this code can load the meal into their own log: its name and numbers, nothing else. It is a copy,
        not a link, so later edits to this meal don't travel with it.
      </p>
      <textarea
        readOnly
        value={code}
        rows={3}
        spellCheck={false}
        aria-label="The code"
        onFocus={(event) => event.currentTarget.select()}
        className="w-full rounded-control border-[1.5px] border-rule bg-field px-3 py-2 font-mono text-base break-all text-ink sm:text-small"
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={copy}>Copy code</Button>
        <span role="status" className="text-small text-ink-2">
          {copied ? 'Copied.' : 'Or select the text above and copy it.'}
        </span>
      </div>
    </section>
  )
}
