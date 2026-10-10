import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, m } from 'motion/react'
import { CloseIcon } from '@/ui/icons'
import { DURATION, SPRING } from '@/lib/motion'

/** DESIGN.md (Components -> Toasts): an ink ground, ground-coloured text, 8px
 *  radius, above the tab bar on phones and bottom-right on desktop. Five
 *  seconds, a close button, and at most one action.
 *
 *  ⚠ A toast vanishes, so it must never be the only way to reach what it
 *  offers (WCAG 2.2.1, timing). Every action passed here has to exist
 *  somewhere permanent too -- the estimate's "View" is also the Log button's
 *  "Ready" state. */
export interface ToastInput {
  text: string
  /** A button, not a link: the one action so far opens the Log panel over
   *  whatever page is showing when it is pressed, which no fixed href knows. */
  action?: { label: string; onSelect: () => void }
}

interface ToastItem extends ToastInput {
  id: number
}

interface ToastApi {
  /** Shows a toast and returns its id, for dismiss(). */
  show: (toast: ToastInput) => number
  dismiss: (id: number) => void
}

const TOAST_MS = 5_000

const ToastContext = createContext<ToastApi | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  // One at a time: a second toast replaces the first rather than stacking. The
  // app only ever has one thing at a time worth interrupting for.
  const [toast, setToast] = useState<ToastItem | null>(null)
  const nextId = useRef(1)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const dismiss = useCallback((id: number) => {
    setToast((current) => (current?.id === id ? null : current))
  }, [])

  const show = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++
      setToast({ ...input, id })
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => dismiss(id), TOAST_MS)
      return id
    },
    [dismiss],
  )

  // Stable, so a provider that keeps it in a dependency list (AnalysisProvider's
  // `watch`) is not rebuilt on every toast.
  const api = useMemo(() => ({ show, dismiss }), [show, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* The live region is always in the page, empty when nothing is showing:
          a region inserted together with its message is not reliably read out. */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-3 left-3 bottom-[calc(var(--shell-bottom)+12px)] z-40 desk:left-auto desk:right-6 desk:bottom-6 desk:w-[400px]"
      >
        <AnimatePresence>
          {toast && (
            <m.div
              key={toast.id}
              role="status"
              className="pointer-events-auto flex items-center gap-2.5 rounded-lg bg-ink py-2.5 pr-2.5 pl-3.5 text-ground"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0, transition: SPRING.toast }}
              exit={{ opacity: 0, y: 8, transition: { duration: DURATION.fast } }}
            >
              <p className="flex-1 text-[14px]">{toast.text}</p>
              {toast.action && (
                <button
                  type="button"
                  onClick={() => {
                    dismiss(toast.id)
                    toast.action?.onSelect()
                  }}
                  className="inline-flex h-[38px] items-center rounded-control border-[1.5px] border-ground px-3 text-[14px] font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ground"
                >
                  {toast.action.label}
                </button>
              )}
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss"
                className="grid size-[38px] place-items-center rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ground"
              >
                <CloseIcon size={18} aria-hidden />
              </button>
            </m.div>
          )}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used within ToastProvider')
  return api
}
