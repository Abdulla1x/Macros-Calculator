import { useEffect, useRef, useState } from 'react'

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

  // The triggers are a meal row or a template pill, either of which can be well
  // away from here. Without this the panel opens off-screen and the tap reads
  // as having done nothing.
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
    <section
      ref={box}
      className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-5"
    >
      <div className="mb-1 flex items-start justify-between gap-3">
        <h2 className="font-semibold">Meal code for “{label}”</h2>
        <button
          onClick={onClose}
          aria-label="Close the meal code panel"
          className="text-xs text-ink-faint hover:text-slate-200"
        >
          ✕
        </button>
      </div>
      <p className="mb-3 text-sm text-slate-400">
        Send this to someone and they can load this meal into their own log and edit
        it. Anyone with the code can read these numbers and the meal name. It is not
        a link to your account, and there is nothing to take back once you have sent
        it — correcting or deleting this meal later does nothing to a code that is
        already out there.
      </p>
      <textarea
        readOnly
        value={code}
        rows={3}
        spellCheck={false}
        onFocus={(event) => event.currentTarget.select()}
        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs break-all text-slate-300"
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={copy}
          className="rounded-lg bg-brand text-brand-ink px-4 py-2 text-sm font-semibold"
        >
          Copy code
        </button>
        <span className="text-xs text-slate-400">
          {copied ? 'Copied ✓' : 'Or select the text above and copy it.'}
        </span>
      </div>
    </section>
  )
}
