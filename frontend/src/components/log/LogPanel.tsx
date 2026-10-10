import { lazy, Suspense, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { AnimatePresence, m } from 'motion/react'
import { Dialog } from 'radix-ui'
import { BackIcon, CloseIcon } from '@/ui/icons'
import { DURATION, EASE_IN, SPRING } from '@/lib/motion'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { LogScreen } from './logPanelUrl'
import { useLogPanel } from './useLogPanel'

// Each screen is its own downloadable piece, like the pages were: the shell is
// in every page's first download, but the AI box and the form are only fetched
// the first time someone opens Log.
const LogStart = lazy(() => import('./LogStart'))
const LogByHand = lazy(() => import('../../pages/LogMeal'))

const ICON_BUTTON =
  'grid size-11 shrink-0 place-items-center rounded-control text-ink hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

/** The Log panel (overhaul 0a; DESIGN.md Layout and Motion): a bottom sheet at
 *  92% height on phones, a 480px panel from the right on desktop, over
 *  whatever page was open. Radix's Dialog supplies the focus trap, Escape,
 *  scroll lock and the return of focus to whatever opened it.
 *
 *  Opened and closed through the address (logPanelUrl.ts), so this component
 *  only follows it: `?log` present means open. */
export default function LogPanel() {
  const location = useLocation()
  const { screen, close, back } = useLogPanel()
  const desk = useMediaQuery('(min-width: 900px)')
  const open = screen !== null

  // While it slides away the address no longer says which screen it was, so
  // the last one is held for the length of the exit.
  const shown = useRef<LogScreen>('start')
  if (screen) shown.current = screen
  const current = screen ?? shown.current

  // What had focus when the panel opened, to hand it back on close. Radix only
  // does this for its own Dialog.Trigger, and this panel has none: it opens
  // from the address (the Log button, a toast, a meal's Edit), so without this
  // focus fell to <body> and a keyboard or screen-reader user was dropped at
  // the top of the page. Read during render, not in an effect: the panel's
  // focus trap mounts inside it and its effect moves focus before any effect
  // here would run.
  const opener = useRef<HTMLElement | null>(null)
  const wasOpen = useRef(false)
  if (open && !wasOpen.current && document.activeElement instanceof HTMLElement) {
    opener.current = document.activeElement
  }
  wasOpen.current = open
  const returnFocus = (event: Event) => {
    event.preventDefault()
    // The opener may be gone (a toast's View button, dismissed by the press);
    // then the Log button that is on screen at this width.
    const target =
      opener.current?.isConnected && opener.current !== document.body
        ? opener.current
        : Array.from(document.querySelectorAll<HTMLElement>('button[aria-haspopup="dialog"]')).find(
            (button) => button.offsetParent !== null,
          )
    // Without scrolling: the page underneath did not move while the panel
    // was open, and after a save it is about to scroll to the top itself.
    target?.focus({ preventScroll: true })
  }

  const state = location.state as { editMeal?: unknown; logFromStart?: boolean } | null
  const title =
    current === 'hand' ? (state?.editMeal ? 'Edit meal' : 'Enter it by hand') : 'Log a meal'
  const canGoBack = current === 'hand' && Boolean(state?.logFromStart)

  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && close()}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <m.div
                className="fixed inset-0 z-50 bg-black/45"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.2 } }}
                exit={{ opacity: 0, transition: { duration: DURATION.base } }}
              />
            </Dialog.Overlay>
            {/* No description: the title and the screen's own headings say
                what this is, and an invented sentence would only add reading. */}
            <Dialog.Content
              asChild
              forceMount
              aria-describedby={undefined}
              // Escape belongs to an open popup inside the panel first: in the
              // food search it should close the suggestions, not throw away a
              // half-entered meal. Radix listens on the document, ahead of the
              // field's own handler, so it has to be told. Anything with a
              // popup says so with aria-expanded (FoodAutocomplete does).
              onCloseAutoFocus={returnFocus}
              onEscapeKeyDown={(event) => {
                if (document.activeElement?.getAttribute('aria-expanded') === 'true') event.preventDefault()
              }}
            >
              <m.div
                className="fixed inset-x-0 bottom-0 z-50 flex h-[92dvh] flex-col rounded-t-sheet border-t border-rule bg-ground text-ink focus:outline-none desk:inset-y-0 desk:right-0 desk:left-auto desk:h-full desk:w-[480px] desk:rounded-none desk:border-t-0 desk:border-l"
                // Rises from the bottom on phones, slides from the right on
                // desktop; a spring in, an ease-in out (DESIGN.md Motion). Under
                // reduced motion MotionConfig keeps only the fade.
                initial={desk ? { x: '100%' } : { y: '100%' }}
                animate={{ x: 0, y: 0, transition: SPRING.panel }}
                exit={
                  desk
                    ? { x: '100%', transition: { duration: DURATION.base, ease: EASE_IN } }
                    : { y: '100%', transition: { duration: DURATION.base, ease: EASE_IN } }
                }
              >
                <div aria-hidden="true" className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-rule desk:hidden" />
                <header className="flex min-h-[54px] shrink-0 items-center gap-1.5 border-b border-rule px-2">
                  {canGoBack ? (
                    <button type="button" onClick={back} aria-label="Back" className={ICON_BUTTON}>
                      <BackIcon size={22} aria-hidden />
                    </button>
                  ) : (
                    <span className="size-11 shrink-0" />
                  )}
                  <Dialog.Title className="flex-1 truncate text-center text-title">{title}</Dialog.Title>
                  <Dialog.Close aria-label="Close" className={ICON_BUTTON}>
                    <CloseIcon size={22} aria-hidden />
                  </Dialog.Close>
                </header>
                <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-4 pb-[calc(env(safe-area-inset-bottom)+28px)] desk:px-7">
                  <Suspense fallback={null}>{current === 'hand' ? <LogByHand /> : <LogStart />}</Suspense>
                </div>
              </m.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  )
}
