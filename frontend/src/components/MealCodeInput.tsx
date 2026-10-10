import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { SharedMeal } from '../types'
import { Button } from '@/ui/button'
import { FIELD } from '@/ui/field'
import { useLiveMessage } from '../hooks/useLiveMessage'

/** Paste a meal code someone sent you, and get their meal in this form.
 *
 * A code is the whole meal, not a link to it, so this reaches nobody's account
 * and nothing is looked up: the server decodes the string and hands back the
 * numbers inside it. What arrives is a draft the user edits and saves as their
 * own row.
 *
 * Collapsed to a single line by default. This is a rarely-used entry point
 * sitting above the two everyday ones, and a permanently-open textarea for it
 * is the clutter the dashboard's Saved meals panel already refuses to be.
 *
 * In its own file rather than inside LogMeal.tsx, which is already one of the
 * larger files here, and because the decode-failure handling below is the sort
 * of thing that gets quietly deleted when it is buried in a bigger component.
 */
export default function MealCodeInput({
  onLoaded,
  startOpen = false,
  onCancel,
}: {
  onLoaded: (shared: SharedMeal, code: string) => void
  /** Open on mount, for a screen that shows its own "Paste a meal code" row
   *  and renders this only once that row is tapped. */
  startOpen?: boolean
  /** Called when the box is closed, so such a screen can show its row again. */
  onCancel?: () => void
}) {
  const [open, setOpen] = useState(startOpen)
  // Focus the box when it opens on a tap (startOpen): the tap was the request
  // to paste, so the caret should already be there.
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (startOpen) box.current?.focus()
  }, [startOpen])
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  useLiveMessage(error)
  const [loading, setLoading] = useState(false)

  const close = () => {
    setOpen(false)
    setCode('')
    setError(null)
    onCancel?.()
  }

  const load = async () => {
    const trimmed = code.trim()
    if (!trimmed) {
      setError('Paste the code first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const shared = await api.decodeMealCode(trimmed)
      onLoaded(shared, trimmed)
      close()
    } catch (err) {
      // The server's refusals are written to be read: "that code is cut short",
      // "that doesn't look like a meal code". Surfacing err.message rather than
      // a generic line is the whole point of their being sentences.
      setError(err instanceof Error ? err.message : 'That code could not be read.')
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-11 text-small text-action underline underline-offset-3"
      >
        Got a meal code from someone? Paste it here
      </button>
    )
  }

  return (
    <section className="grid gap-2">
      <h3 className="text-field-label text-ink-2">Paste a meal code</h3>
      <p className="text-small text-ink-2">
        Codes are long, so paste the whole thing. Nothing is sent to whoever gave it to you, and
        they are not told you used it.
      </p>
      <textarea
        ref={box}
        value={code}
        onChange={(event) => setCode(event.target.value)}
        rows={3}
        spellCheck={false}
        aria-label="Meal code"
        placeholder="MC1..."
        className={`${FIELD} py-2.5 font-mono break-all`}
      />
      {/* Ink and words, never red (DESIGN.md). */}
      {error && <p className="border-l-2 border-ink pl-3 text-small">{error}</p>}
      <div className="flex gap-2">
        <Button type="button" onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Load meal'}
        </Button>
        <Button type="button" variant="ghost" onClick={close}>
          Cancel
        </Button>
      </div>
    </section>
  )
}
