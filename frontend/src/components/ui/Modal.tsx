import { useEffect, useRef, type ReactNode } from 'react'

// Everything the browser will let you Tab to. `:not([disabled])` matters on the
// two that can be disabled -- a disabled button is still matched by `button`,
// and including it puts a dead stop in the middle of the trap.
const FOCUSABLE =
  'a[href],button:not([disabled]),textarea,input:not([disabled]),select,[tabindex]:not([tabindex="-1"])'

/** The shared shell for every modal in the app: backdrop, panel, and the four
 *  behaviours a dialog has to have.
 *
 *  Two dialogs each retyped the backdrop line and then drifted -- one on
 *  rounded-xl/slate-800/slate-900, the other on the rounded-card/line/surface
 *  tokens, which resolve to the same three values, so the duplication was
 *  invisible right up until someone changed one of them. AlertDialog's docblock
 *  had claimed for two phases that they shared a shell. They did not. Now they
 *  do.
 *
 *  What neither of them had, and both now get:
 *
 *    * Escape closes.
 *    * Tab stays inside. Without this a screen-reader or keyboard user tabs
 *      straight out of the dialog into the page it is covering, and there is no
 *      visible cue they have left.
 *    * Background scroll is locked. The page scrolls on <body> here -- the shell
 *      is `min-h-screen` with no overflow container -- so overflow:hidden on the
 *      body is the whole fix.
 *    * Focus returns to whatever opened the dialog when it closes.
 *
 *  Deliberately NOT added: click-the-backdrop-to-close. It is wrong on an
 *  alertdialog, where the point is that a refused value has to be acknowledged
 *  rather than dismissed by a stray tap, and having it on one dialog but not the
 *  other is how the drift above started.
 *
 *  This renders exactly the two elements the call sites rendered before it, with
 *  the same tags and attributes, so scripts/dom-snapshot.mjs sees no change. The
 *  panel ref and the listeners are not DOM. */
export default function Modal({
  label,
  onClose,
  role = 'dialog',
  panelClassName = '',
  children,
}: {
  /** The dialog's accessible name. */
  label: string
  onClose: () => void
  /** `alertdialog` for a message that interrupts, `dialog` for one you opened. */
  role?: 'dialog' | 'alertdialog'
  /** Appended last, so a call site can still win. AnnouncementsModal needs
   *  max-h/overflow because its content is a list of unknown length. */
  panelClassName?: string
  children: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  // The setup effect below must run exactly once per open. Call sites pass an
  // inline arrow or a function rebuilt each render, so `onClose` in the
  // dependency list would re-run it on every parent render -- re-locking scroll,
  // and re-stealing focus out from under whatever the user had just tabbed to.
  // The ref keeps the effect stable while still calling the current handler.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    const panel = panelRef.current
    if (panel === null) return

    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null

    // Only if nothing inside has already claimed focus: AlertDialog's OK button
    // carries autoFocus and React has already focused it by the time this runs.
    if (!panel.contains(document.activeElement)) {
      panel.querySelector<HTMLElement>(FOCUSABLE)?.focus()
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (first === undefined || last === undefined) return

      // Focus outside the panel is treated as "before the first stop", which is
      // what happens if the page behind ever manages to take it back.
      const active = document.activeElement
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      opener?.focus()
    }
  }, [])

  return (
    <div
      role={role}
      aria-modal="true"
      aria-label={label}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div
        ref={panelRef}
        className={`w-full max-w-md rounded-card border border-line bg-surface p-5 ${panelClassName}`}
      >
        {children}
      </div>
    </div>
  )
}
