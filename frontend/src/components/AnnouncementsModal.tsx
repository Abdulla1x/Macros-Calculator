import { useEffect, useState } from 'react'
import { parseIsoDate } from '../lib/dates'
import { markAnnouncementsSeen, seenAnnouncementIds } from '../lib/dismissals'
import type { Announcement } from '../types'

// A + alias, not the bare personal address: inbound mail stays filterable, and
// the address is disposable once scrapers find it in this very public DOM.
const CONTACT_EMAIL = 'm.abdulla992003+macros@gmail.com'

/** "What's new", shown once per release note per device.
 *
 * Dismissal is per-id rather than a single "last seen" marker so that adding an
 * older-dated note, or shipping two at once, can't silently skip one. */
export default function AnnouncementsModal({ items }: { items: Announcement[] }) {
  const [unseen, setUnseen] = useState<Announcement[]>([])

  useEffect(() => {
    const seen = seenAnnouncementIds()
    setUnseen(items.filter((item) => !seen.includes(item.id)))
  }, [items])

  if (unseen.length === 0) return null

  const close = () => {
    markAnnouncementsSeen(unseen.map((item) => item.id))
    setUnseen([])
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="What's new"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">✨ What's new</h2>
          <button
            onClick={close}
            aria-label="Close"
            className="text-slate-500 hover:text-slate-300"
          >
            ✕
          </button>
        </div>

        <ul className="space-y-4">
          {unseen.map((item) => (
            <li key={item.id} className="rounded-lg border border-slate-800 bg-slate-800/40 p-3">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-sm font-semibold text-emerald-300">{item.title}</h3>
                <time
                  dateTime={item.date}
                  className="shrink-0 text-[11px] text-slate-500"
                >
                  {parseIsoDate(item.date).toLocaleDateString(undefined, {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                  })}
                </time>
              </div>
              <p className="mt-1.5 text-sm text-slate-300">{item.body}</p>
            </li>
          ))}
        </ul>

        <button
          onClick={close}
          className="mt-5 w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
        >
          Got it
        </button>

        <p className="mt-3 text-center text-xs text-slate-500">
          Found a bug or want something?{' '}
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="text-emerald-400 hover:text-emerald-300"
          >
            {CONTACT_EMAIL}
          </a>
        </p>
      </div>
    </div>
  )
}
