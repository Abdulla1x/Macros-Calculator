import Modal from './ui/Modal'
import Button from './ui/Button'

/** A blocking "that didn't work" dialog.
 *
 * Deliberately a modal rather than inline help text. The bounds on the body
 * profile fields are explained under each input already, and that explanation
 * is exactly what someone skips on the way to typing a number — so the moment
 * a value is actually refused, the app has to interrupt rather than annotate.
 *
 * It now genuinely does share a shell with AnnouncementsModal — ui/Modal — which
 * two earlier versions of this comment claimed before it was true. The shell
 * also brought Escape-to-close, a focus trap, background scroll lock and focus
 * restore, none of which either dialog had.
 *
 * role="alertdialog" rather than "dialog", and the shell deliberately has no
 * click-the-backdrop-to-close: this one interrupts to report a refusal, and a
 * refusal that a stray tap dismisses has not been read. */
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
    <Modal role="alertdialog" label={title} onClose={onClose}>
      <h2 className="mb-2 text-lg font-semibold text-amber-300">{title}</h2>
      <p className="text-sm text-slate-300">{message}</p>
      <Button
        onClick={onClose}
        autoFocus
        className="mt-5 w-full px-5 py-2"
      >
        OK
      </Button>
    </Modal>
  )
}
