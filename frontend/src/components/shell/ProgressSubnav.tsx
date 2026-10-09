import { Link } from 'react-router-dom'
import { PROGRESS_PAGES } from './sections'

/** Nutrition · Weight · Weekly review, at the top of each of those pages.
 *
 *  Interim, and deliberately plain: the Progress tab opens Analytics, and
 *  without this the other two pages would have no way in from the nav. Phase 2
 *  merges them into one Progress screen and deletes this. Chips as DESIGN.md
 *  draws them: 36px, a 1.5px rule border, the current one filled with ink. */
export default function ProgressSubnav({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Progress sections" className="mb-5 flex flex-wrap gap-1.5">
      {PROGRESS_PAGES.map((page) => {
        const current = pathname === page.to
        return (
          <Link
            key={page.to}
            to={page.to}
            aria-current={current ? 'page' : undefined}
            className={`inline-flex h-9 items-center rounded-control border-[1.5px] px-3 text-[13.5px] font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action ${
              current ? 'border-ink bg-ink text-ground' : 'border-rule text-ink hover:border-ink'
            }`}
          >
            {page.label}
          </Link>
        )
      })}
    </nav>
  )
}
