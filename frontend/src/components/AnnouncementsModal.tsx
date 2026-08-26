import { useEffect, useState } from 'react'
import { parseIsoDate } from '../lib/dates'
import { markAnnouncementsSeen, seenAnnouncementIds } from '../lib/dismissals'
import type { Announcement } from '../types'

// A + alias, not the bare personal address: inbound mail stays filterable, and
// the address is disposable once scrapers find it in this very public DOM.
const CONTACT_EMAIL = 'm.abdulla992003+macros@gmail.com'

// Announcement bodies are written in a deliberately tiny subset of Markdown:
// blank-line paragraph breaks, **bold** and *italic*. That is everything the
// bodies in announcements.py use, and everything supported -- more would want a
// real parser, and a dependency for three constructs is a poor trade. If a note
// ever needs a list or a link, this is the place that has to learn them, and it
// will be obvious because they will appear on screen as punctuation.
//
// This matters more than it looks, and it shipped wrong. `item.body` used to go
// straight into a single <p>, where HTML collapses the blank lines: every note
// arrived as one unbroken wall of text, and three of them printed their **
// markers literally. Nothing in code review shows that -- the string is correct
// and the JSX is valid -- it is only visible on screen.
const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*)/g

function inline(text: string, key: string) {
  return text
    .split(INLINE)
    .filter((part) => part !== '')
    .map((part, index) => {
      const id = `${key}-${index}`
      // Bold is tested first because the alternation above prefers it, so a
      // `**word**` run never reaches the italic branch.
      if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={id} className="font-semibold text-slate-100">
            {part.slice(2, -2)}
          </strong>
        )
      }
      if (part.length > 2 && part.startsWith('*') && part.endsWith('*')) {
        return <em key={id}>{part.slice(1, -1)}</em>
      }
      return <span key={id}>{part}</span>
    })
}

function AnnouncementBody({ text }: { text: string }) {
  return (
    <div className="mt-1.5 space-y-2 text-sm text-slate-300">
      {text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index}>{inline(paragraph, String(index))}</p>
      ))}
    </div>
  )
}

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
            className="text-ink-faint hover:text-slate-300"
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
                  className="shrink-0 text-[11px] text-ink-faint"
                >
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

        <button
          onClick={close}
          className="mt-5 w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
        >
          Got it
        </button>

        <p className="mt-3 text-center text-xs text-ink-faint">
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
