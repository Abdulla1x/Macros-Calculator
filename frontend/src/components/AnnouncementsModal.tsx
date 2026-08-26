import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { parseIsoDate } from '../lib/dates'
import {
  hasEverSeenAnnouncements,
  markAnnouncementsSeen,
  seenAnnouncementIds,
} from '../lib/dismissals'
import type { Announcement } from '../types'
import AnnouncementBody from './AnnouncementBody'

// A + alias, not the bare personal address: inbound mail stays filterable, and
// the address is disposable once scrapers find it in this very public DOM.
const CONTACT_EMAIL = 'm.abdulla992003+macros@gmail.com'

// Rolling cap, and it has to stay rolling: every session that ships adds a note,
// so an uncapped modal only ever grows. Measured before capping -- a fresh
// signup got all 18 notes at 11,106px of content inside a 661px window, roughly
// seventeen screens, over a page it also blocked every click on.
const MAX_MODAL_NOTES = 3

type View =
  | { kind: 'hidden' }
  | { kind: 'welcome'; total: number }
  | { kind: 'notes'; shown: Announcement[]; pending: string[]; remaining: number }

/** "What's new", shown once per release note per device.
 *
 * Dismissal is per-id rather than a single "last seen" marker so that adding an
 * older-dated note, or shipping two at once, can't silently skip one. */
export default function AnnouncementsModal({ items }: { items: Announcement[] }) {
  const [view, setView] = useState<View>({ kind: 'hidden' })

  useEffect(() => {
    if (items.length === 0) return

    // First run on this device. Every note is marked seen without being shown:
    // the backlog is history this account was not present for, and a changelog
    // is the wrong first thing to meet. Capping the *display* while leaving the
    // rest unseen would be worse than not capping -- the next reload would serve
    // the next three, and the one after that the next three.
    if (!hasEverSeenAnnouncements()) {
      markAnnouncementsSeen(items.map((item) => item.id))
      setView({ kind: 'welcome', total: items.length })
      return
    }

    const seen = seenAnnouncementIds()
    const unseen = items.filter((item) => !seen.includes(item.id))
    if (unseen.length === 0) {
      setView({ kind: 'hidden' })
      return
    }
    setView({
      kind: 'notes',
      shown: unseen.slice(0, MAX_MODAL_NOTES),
      pending: unseen.map((item) => item.id),
      remaining: Math.max(0, unseen.length - MAX_MODAL_NOTES),
    })
  }, [items])

  if (view.kind === 'hidden') return null

  const close = () => {
    // Every unseen id, not only the ones displayed. Marking just the shown three
    // is exactly what turns a cap into a dismiss-three-reload-repeat gauntlet.
    // Nothing is lost by marking the rest: /whats-new keeps the full list.
    if (view.kind === 'notes') markAnnouncementsSeen(view.pending)
    setView({ kind: 'hidden' })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="What's new"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-card border border-line bg-surface p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {view.kind === 'welcome' ? '✨ Welcome' : '✨ What’s new'}
          </h2>
          <button onClick={close} aria-label="Close" className="text-ink-faint hover:text-slate-300">
            ✕
          </button>
        </div>

        {view.kind === 'welcome' ? (
          <p className="text-sm text-slate-300">
            You’re all set — there’s nothing to catch up on. The {view.total} release notes
            written before you arrived are in{' '}
            <Link to="/whats-new" className="text-emerald-400 hover:text-emerald-300">
              What’s new
            </Link>{' '}
            if you ever want the history.
          </p>
        ) : (
          <>
            <ul className="space-y-4">
              {view.shown.map((item) => (
                <li key={item.id} className="rounded-control border border-line bg-slate-800/40 p-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="text-sm font-semibold text-emerald-300">{item.title}</h3>
                    <time dateTime={item.date} className="shrink-0 text-[11px] text-ink-faint">
                      {parseIsoDate(item.date).toLocaleDateString(undefined, {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </time>
                  </div>
                  <AnnouncementBody text={item.body} />
                </li>
              ))}
            </ul>
            {view.remaining > 0 && (
              <p className="mt-3 text-center text-xs text-ink-faint">
                and {view.remaining} older {view.remaining === 1 ? 'note' : 'notes'} in{' '}
                <Link to="/whats-new" className="text-emerald-400 hover:text-emerald-300">
                  What’s new
                </Link>
              </p>
            )}
          </>
        )}

        <button
          onClick={close}
          className="mt-5 w-full rounded-control bg-brand px-5 py-2 text-sm font-semibold text-brand-ink hover:bg-emerald-400"
        >
          Got it
        </button>

        <p className="mt-3 text-center text-xs text-ink-faint">
          Found a bug or want something?{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="text-emerald-400 hover:text-emerald-300">
            {CONTACT_EMAIL}
          </a>
        </p>
      </div>
    </div>
  )
}
