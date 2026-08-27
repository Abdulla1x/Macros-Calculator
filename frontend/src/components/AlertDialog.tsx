/** A blocking "that didn't work" dialog.
 *
 * Deliberately a modal rather than inline help text. The bounds on the body
 * profile fields are explained under each input already, and that explanation
 * is exactly what someone skips on the way to typing a number — so the moment
 * a value is actually refused, the app has to interrupt rather than annotate.
 *
 * It does NOT share a shell with AnnouncementsModal, whatever an earlier
 * version of this comment claimed. Only the backdrop line is identical; the
 * panel differs already (rounded-xl/slate-800/slate-900 here, the semantic
 * rounded-card/line/surface tokens there), which is exactly the drift the old
 * claim said could not happen. Neither dialog closes on Escape, traps focus, or
 * locks background scroll.
 *
 * Deliberately not fixed here: one shared ui/Modal carrying all three is the
 * primitive migration's job, and hand-patching two copies in the meantime is
 * how you end up with three. Recorded rather than quietly left, because a
 * comment asserting a rule its own contents break is a trap this repo has paid
 * for more than once. */
export default function AlertDialog({
  title,
  message,
  onClose,
}: {
  title: string
  message: string
  onClose: () => void
}) {
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-2 text-lg font-semibold text-amber-300">{title}</h2>
        <p className="text-sm text-slate-300">{message}</p>
        <button
          onClick={onClose}
          autoFocus
          className="mt-5 w-full rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
        >
          OK
        </button>
      </div>
    </div>
  )
}
