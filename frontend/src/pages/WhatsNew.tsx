import { useEffect, useState } from 'react'
import AnnouncementBody from '../components/AnnouncementBody'
import { useAnnouncements } from '../hooks/useAnnouncements'
import { parseIsoDate } from '../lib/dates'

// useAnnouncements returns null both while the fetch is in flight and when it
// failed -- it fails silently by design, because everywhere else the notes are
// decoration. On this page they are the entire content, so a permanent
// "Loading…" would be a claim that is false half the time. Same shape as
// Layout's COLD_START_NOTICE_AFTER_MS: say nothing until the wait stops looking
// normal, then say something true.
const GAVE_UP_AFTER_MS = 8_000

export default function WhatsNew() {
  const announcements = useAnnouncements()
  const [gaveUp, setGaveUp] = useState(false)

  useEffect(() => {
    if (announcements !== null) {
      setGaveUp(false)
      return
    }
    const timer = setTimeout(() => setGaveUp(true), GAVE_UP_AFTER_MS)
    return () => clearTimeout(timer)
  }, [announcements])

  const items = announcements?.items ?? []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">What’s new</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Every release note, newest first. The pop-up only ever shows the newest few, so this
          is where the rest live.
        </p>
      </header>

      {announcements === null ? (
        <p className="text-sm text-ink-faint">
          {gaveUp ? 'Could not load the release notes just now. Try again later.' : 'Loading…'}
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-ink-faint">No release notes yet.</p>
      ) : (
        <ul className="space-y-4">
          {items.map((item) => (
            <li key={item.id} className="rounded-card border border-line bg-surface p-5">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-sm font-semibold text-emerald-300">{item.title}</h2>
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
      )}
    </div>
  )
}
