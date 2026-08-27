import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import {
  MAX_SUPPLEMENT_DOSE,
  MAX_SUPPLEMENT_NAME,
  MAX_SUPPLEMENT_TIMES,
  MAX_SUPPLEMENTS,
  validateSupplement,
} from '../../lib/limits'
import type { Supplement } from '../../types'

/** The supplement list: add, edit, pause, delete.
 *
 * The one section on the Trackers tab that saves as you go. The water and step
 * goals above it are columns on the single `settings` row, so they edit a draft
 * and wait for the Save bar; a supplement is a row in its own table with its
 * own endpoints, and holding those in a draft would mean a half-typed
 * supplement silently lost by navigating away.
 *
 * Mixed save semantics on one tab is a real cost, so it is paid twice over: the
 * copy says which model this is, and the Save bar stays away when you tick
 * something here, which says the same thing without words.
 */
export default function SupplementsSection({
  onRejected,
}: {
  onRejected: (message: string) => void
}) {
  const [items, setItems] = useState<Supplement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState({ name: '', dose: '', times: ['08:00'] })
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    setLoading(true)
    api
      .getSupplements()
      .then((next) => {
        setItems(next)
        setError('')
      })
      // An empty list and a failed fetch look identical once rendered, and one
      // of them means "add your first" while the other means "try again".
      .catch(() => setError("Couldn't load your supplements."))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  // Opening or abandoning a form clears the last failure with it. A refusal
  // like "you already track creatine" answers the attempt that caused it, and
  // leaving it on screen once that attempt is gone makes it read as a standing
  // problem with the section rather than a rejected keystroke.
  const startAdd = () => {
    setError('')
    setDraft({ name: '', dose: '', times: ['08:00'] })
    setEditing('new')
  }

  const startEdit = (item: Supplement) => {
    setError('')
    setDraft({ name: item.name, dose: item.dose ?? '', times: [...item.times] })
    setEditing(item.id)
  }

  const cancelEdit = () => {
    setError('')
    setEditing(null)
  }

  // `map`, not an indexed assignment into a copy. Assigning past the end of a
  // shortened array leaves a hole, JSON.stringify writes the hole as `null`,
  // and the server refuses with a 422 about a field the user cannot see is
  // wrong — the exact bug the water quick-adds shipped and had to have fixed.
  // map cannot produce a hole and cannot write past the end.
  const setTime = (index: number, value: string) =>
    setDraft((current) => ({
      ...current,
      times: current.times.map((time, i) => (i === index ? value : time)),
    }))

  const removeTime = (index: number) =>
    setDraft((current) => ({
      ...current,
      times: current.times.filter((_, i) => i !== index),
    }))

  const save = async () => {
    // Empty boxes are dropped rather than sent: clearing a time input yields
    // "", which is a row the user is done with, not a time.
    const times = draft.times.filter((time) => time !== '')
    const problem = validateSupplement(draft.name, draft.dose, times)
    if (problem) {
      onRejected(problem)
      return
    }
    const body = {
      name: draft.name.trim(),
      dose: draft.dose.trim() || null,
      times,
      // Editing never changes the paused state — that is the toggle's job, and
      // a Save that silently un-paused something would be a surprise.
      active: editing === 'new'
        ? true
        : (items.find((item) => item.id === editing)?.active ?? true),
    }
    setBusy(true)
    try {
      if (editing === 'new') await api.createSupplement(body)
      else if (typeof editing === 'number') await api.updateSupplement(editing, body)
      setEditing(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const togglePause = async (item: Supplement) => {
    setBusy(true)
    try {
      await api.updateSupplement(item.id, {
        name: item.name,
        dose: item.dose,
        times: item.times,
        active: !item.active,
      })
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that — try again.')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteSupplement(id)
      setConfirmDelete(null)
      setError('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h2 className="mb-1 font-semibold">💊 Supplements</h2>
      <p className="mb-4 text-sm text-slate-400">
        What you take, and when. Each time you add becomes a box to tick on your
        dashboard. The card will tell you when a dose is overdue while the app
        is open — and that is the whole of it:{' '}
        <strong className="text-slate-300">
          nothing here will notify you on your phone
        </strong>
        . Push notifications on Android go through Google Play Services and
        scheduled local ones need a browser feature that was never built, so a
        reminder that reached you with the app closed is not something this app
        can deliver. Changes in this section save straight away — the Save bar
        is for the water and step goals above.
      </p>

      {loading ? (
        <p className="text-sm text-ink-faint">Loading…</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
            >
              {editing === item.id ? (
                <SupplementForm
                  draft={draft}
                  setDraft={setDraft}
                  setTime={setTime}
                  removeTime={removeTime}
                  onSave={save}
                  onCancel={cancelEdit}
                  busy={busy}
                />
              ) : (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  <span className={item.active ? 'text-slate-200' : 'text-ink-faint'}>
                    {item.name}
                    {item.dose && (
                      <span className="ml-1.5 text-xs text-ink-faint">{item.dose}</span>
                    )}
                  </span>
                  <span className="text-xs tabular-nums text-ink-faint">
                    {item.times.join(' · ')}
                  </span>
                  {!item.active && (
                    <span className="rounded-full bg-slate-700/60 px-2 py-0.5 text-xs text-slate-400">
                      paused
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-2 text-xs">
                    <button
                      onClick={() => startEdit(item)}
                      disabled={busy}
                      className="text-slate-400 hover:text-emerald-300 disabled:opacity-40"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => togglePause(item)}
                      disabled={busy}
                      className="text-slate-400 hover:text-amber-300 disabled:opacity-40"
                    >
                      {item.active ? 'Pause' : 'Resume'}
                    </button>
                    {confirmDelete === item.id ? (
                      <>
                        <button
                          onClick={() => remove(item.id)}
                          disabled={busy}
                          className="rounded border border-rose-500/50 bg-rose-500/10 px-2 py-0.5 text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
                        >
                          Delete for good
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-slate-400 hover:text-slate-200"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(item.id)}
                        disabled={busy}
                        aria-label={`Delete ${item.name}`}
                        className="text-ink-faint hover:text-rose-400 disabled:opacity-40"
                      >
                        Delete
                      </button>
                    )}
                  </span>
                  {/* Spelled out rather than left to be discovered, because
                      the non-destructive option is right next to it and one of
                      the two is unrecoverable. */}
                  {confirmDelete === item.id && (
                    <p className="w-full text-xs text-rose-300">
                      Every dose you have ever ticked for {item.name} goes with
                      it. Pause instead if you are only stopping for now — that
                      keeps the history.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing === 'new' ? (
        <div className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
          <SupplementForm
            draft={draft}
            setDraft={setDraft}
            setTime={setTime}
            removeTime={removeTime}
            onSave={save}
            onCancel={cancelEdit}
            busy={busy}
          />
        </div>
      ) : (
        <button
          onClick={startAdd}
          disabled={busy || items.length >= MAX_SUPPLEMENTS}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
        >
          + Add a supplement
        </button>
      )}

      {items.length >= MAX_SUPPLEMENTS && (
        <p className="mt-2 text-xs text-ink-faint">
          That is the {MAX_SUPPLEMENTS}-supplement limit — a tick list longer
          than that stops being one you can actually read every day.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
    </section>
  )
}

/** The add/edit form. One component for both, because they are the same fields
 *  and two copies would drift. */
function SupplementForm({
  draft,
  setDraft,
  setTime,
  removeTime,
  onSave,
  onCancel,
  busy,
}: {
  draft: { name: string; dose: string; times: string[] }
  setDraft: (next: { name: string; dose: string; times: string[] }) => void
  setTime: (index: number, value: string) => void
  removeTime: (index: number) => void
  onSave: () => void
  onCancel: () => void
  busy: boolean
}) {
  const field =
    'rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-base text-slate-200 sm:text-sm focus:border-emerald-500'

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input
          value={draft.name}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          maxLength={MAX_SUPPLEMENT_NAME}
          placeholder="Name"
          aria-label="Supplement name"
          className={`${field} min-w-0 flex-1`}
        />
        <input
          value={draft.dose}
          onChange={(event) => setDraft({ ...draft, dose: event.target.value })}
          maxLength={MAX_SUPPLEMENT_DOSE}
          placeholder="Dose (optional)"
          aria-label="Dose"
          className={`${field} w-36`}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {draft.times.map((time, index) => (
          // Index as the key, unusually and deliberately: the times are edited
          // in place and two rows can legitimately hold the same value while
          // someone is mid-typing, so the value is not a stable identity.
          <span key={index} className="flex items-stretch">
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(index, event.target.value)}
              aria-label={`Time ${index + 1}`}
              className={`${field} rounded-r-none`}
            />
            <button
              onClick={() => removeTime(index)}
              aria-label={`Remove time ${index + 1}`}
              className="rounded-r-lg border border-l-0 border-slate-700 px-2 text-xs text-ink-faint hover:text-rose-400"
            >
              ✕
            </button>
          </span>
        ))}
        {draft.times.length < MAX_SUPPLEMENT_TIMES && (
          <button
            onClick={() => setDraft({ ...draft, times: [...draft.times, '12:00'] })}
            className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
          >
            + time
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="text-sm text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
