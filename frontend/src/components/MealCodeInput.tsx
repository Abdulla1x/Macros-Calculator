import { useState } from 'react'
import { api } from '../api/client'
import type { SharedMeal } from '../types'

/** Paste a meal code someone sent you, and get their meal in this form.
 *
 * A code is the whole meal, not a link to it, so this reaches nobody's account
 * and nothing is looked up: the server decodes the string and hands back the
 * numbers inside it. What arrives is a draft the user edits and saves as their
 * own row.
 *
 * Collapsed to a single line by default. This is a rarely-used entry point
 * sitting above the two everyday ones, and a permanently-open textarea for it
 * is the clutter the dashboard's Quick log panel already refuses to be.
 *
 * In its own file rather than inside LogMeal.tsx, which is already one of the
 * larger files here, and because the decode-failure handling below is the sort
 * of thing that gets quietly deleted when it is buried in a bigger component.
 */
export default function MealCodeInput({
  onLoaded,
}: {
  onLoaded: (shared: SharedMeal, code: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const close = () => {
    setOpen(false)
    setCode('')
    setError(null)
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
        className="text-sm text-slate-400 underline underline-offset-4 hover:text-slate-200"
      >
        Got a meal code from someone? Paste it here
      </button>
    )
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-1 text-sm font-semibold text-slate-300">Paste a meal code</h2>
      <p className="mb-3 text-sm text-slate-400">
        Codes are long — paste the whole thing. Nothing is sent to whoever gave it to
        you, and they are not told you used it.
      </p>
      <textarea
        value={code}
        onChange={(event) => setCode(event.target.value)}
        rows={3}
        spellCheck={false}
        placeholder="MC1..."
        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-base break-all text-slate-200 sm:text-xs"
      />
      {error && <p className="mt-2 text-sm text-amber-300">{error}</p>}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-lg bg-brand text-brand-ink px-4 py-2 text-sm font-semibold disabled:opacity-50"
        >
          {loading ? 'Loading…' : 'Load meal'}
        </button>
        <button
          type="button"
          onClick={close}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </section>
  )
}
