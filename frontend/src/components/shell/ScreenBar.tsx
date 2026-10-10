import { Link } from 'react-router-dom'
import { BackIcon } from '@/ui/icons'

/** The top of a screen pushed from a tab (DESIGN.md: the day in detail, meal
 *  screens): back on the left, the screen's title in the middle. Back is a
 *  link to a fixed place rather than "history back", so it still leads
 *  somewhere sensible when the screen was opened from a bookmark or reload. */
export default function ScreenBar({ title, back, backLabel }: { title: string; back: string; backLabel: string }) {
  return (
    <header className="grid grid-cols-[44px_minmax(0,1fr)_44px] items-center border-b border-rule pb-1.5">
      <Link
        to={back}
        aria-label={backLabel}
        className="grid size-11 place-items-center rounded-control text-ink hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        <BackIcon size={22} />
      </Link>
      <h1 className="truncate text-center text-title">{title}</h1>
    </header>
  )
}
