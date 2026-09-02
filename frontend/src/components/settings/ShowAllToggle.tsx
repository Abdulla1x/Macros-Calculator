/** "Show all 62 foods" / "Show fewer", under a list that renders only its first
 *  few rows.
 *
 * Both library sections grew unbounded, and the controls that act on them sit
 * *after* the list: `+ Add a food` was below every row a user had, which is the
 * whole reason it could not be found. Capping the rows is what puts those
 * controls back on the first screen.
 *
 * Shared rather than copied because the wording is the part that drifts. The
 * slicing is one `.slice()` per caller and stays there, so each section keeps
 * deciding for itself what "the list" is -- FoodLibrarySection caps the
 * *filtered* array, not the whole library, so a filter that already narrows to
 * three results is not then asked to expand.
 *
 * Not a components/ui/ primitive: those exist to settle colliding Tailwind
 * utilities behind variant props (see ui/Button.tsx), and this has none to
 * settle. It is one button with one job in two files.
 */
/** How many rows a capped list shows before it asks.
 *
 * Lives here rather than in either section so the two cannot drift apart: the
 * Library tab stacks them, and one list breaking at five while the next breaks
 * at ten would read as a bug in whichever you saw second.
 *
 * Five is enough to recognise a list for what it is, and short enough that the
 * controls belonging to it -- "+ Add a food", the filter, the whole Saved meals
 * section underneath -- stay on the first screen.
 */
export const COLLAPSED_ROWS = 5

export default function ShowAllToggle({
  total,
  cap,
  expanded,
  onToggle,
  noun,
}: {
  total: number
  cap: number
  expanded: boolean
  onToggle: () => void
  /** Singular; pluralised here so both call sites cannot disagree about it. */
  noun: string
}) {
  // Nothing to expand, so no control. Rendering a disabled or no-op button for a
  // short list would be one more thing between the user and the list itself.
  if (total <= cap) return null

  return (
    <button
      onClick={onToggle}
      aria-expanded={expanded}
      className="mb-3 w-full rounded-control border border-dashed border-line-strong py-2 text-sm text-ink-muted hover:border-brand hover:text-brand"
    >
      {expanded
        ? 'Show fewer'
        : `Show all ${total} ${noun}${total === 1 ? '' : 's'}`}
    </button>
  )
}
