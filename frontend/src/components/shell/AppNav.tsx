import { useLayoutEffect, useRef, useState, type ComponentType, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { m } from 'motion/react'
import { Button } from '@/ui/button'
import { LogIcon, ProgressIcon, TodayIcon, YouIcon } from '@/ui/icons'
import { useAnalysis } from '@/analysis/AnalysisContext'
import { logButtonLabel, logButtonState } from './logButton'
import { SECTION_HOME, type Section } from './sections'

type IconProps = { size?: number; weight?: 'regular' | 'fill'; 'aria-hidden'?: boolean }

const TABS: { section: Exclude<Section, 'log'>; label: string; Icon: ComponentType<IconProps> }[] = [
  { section: 'today', label: 'Today', Icon: TodayIcon },
  { section: 'progress', label: 'Progress', Icon: ProgressIcon },
  { section: 'you', label: 'You', Icon: YouIcon },
]

/** Where the current tab sits inside `container`, along one axis, so the
 *  marker can slide to it. Re-measured on resize. Null when no tab is current
 *  (the Log page, Admin, an unknown address) or the nav is hidden at this
 *  width, so the marker hides instead of pointing at nothing. */
function useMarker(container: RefObject<HTMLElement | null>, active: Section | null, axis: 'x' | 'y') {
  const [box, setBox] = useState<{ offset: number; size: number } | null>(null)
  useLayoutEffect(() => {
    const element = container.current
    if (!element) return
    const measure = () => {
      const target = active && element.querySelector<HTMLElement>(`[data-section="${active}"]`)
      if (!target || element.offsetParent === null) {
        setBox(null)
        return
      }
      const outer = element.getBoundingClientRect()
      const inner = target.getBoundingClientRect()
      setBox(
        axis === 'x'
          ? { offset: inner.left - outer.left, size: inner.width }
          : { offset: inner.top - outer.top, size: inner.height },
      )
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [container, active, axis])
  return box
}

/** The marker itself. `initial={false}` renders it in place on first paint,
 *  before Motion's features have loaded; later changes slide it. Under the
 *  phone's reduce-motion setting MotionConfig drops the slide and it jumps.
 *  Its size is set directly, not animated, so nothing but the transform moves. */
function Marker({ box, axis, className }: { box: { offset: number; size: number } | null; axis: 'x' | 'y'; className: string }) {
  if (!box) return null
  return (
    <m.span
      aria-hidden="true"
      className={`pointer-events-none absolute bg-ink ${className}`}
      style={axis === 'x' ? { width: box.size } : { height: box.size }}
      initial={false}
      animate={axis === 'x' ? { x: box.offset } : { y: box.offset }}
    />
  )
}

function TabLink({
  section,
  label,
  Icon,
  active,
  className,
}: (typeof TABS)[number] & { active: boolean; className: string }) {
  return (
    <Link
      to={SECTION_HOME[section]}
      data-section={section}
      aria-current={active ? 'page' : undefined}
      className={`${className} ${active ? 'font-bold text-ink' : 'text-ink-2 hover:text-ink'}`}
    >
      {/* Filled for the current tab, regular otherwise (DESIGN.md): the shape
          says "here" as well as the weight and colour do. */}
      <Icon size={22} weight={active ? 'fill' : 'regular'} aria-hidden />
      <span>{label}</span>
    </Link>
  )
}

/** The Log action. A link, because today it opens the Log page; phase 2 turns
 *  it into the button that opens the Log panel. "Log" in the tab bar, where the
 *  middle slot needs a short label (0a), "Log a meal" in the wider rail.
 *
 *  It also carries the AI estimate running in the background (AnalysisProvider):
 *  a spinner while it works, a dot and "Ready" when it landed unseen. */
function LogAction({ active, place, className = '' }: { active: boolean; place: 'bar' | 'rail'; className?: string }) {
  const { analyzing, unseen } = useAnalysis()
  const state = logButtonState(analyzing, unseen)
  const { visible, spoken } = logButtonLabel(place, state)
  return (
    <Button asChild variant="log" size="log" className={className}>
      <Link to={SECTION_HOME.log} aria-current={active ? 'page' : undefined} aria-label={spoken}>
        {state === 'working' ? (
          // A ring with a gap, turning. Under reduced motion the loop stops and
          // the ring stays, so it still reads as "busy" (DESIGN.md: loops stop).
          <span
            aria-hidden="true"
            className="size-[18px] rounded-full border-[2.5px] border-current border-r-transparent motion-safe:animate-spin"
          />
        ) : state === 'ready' ? (
          <span aria-hidden="true" className="size-2.5 rounded-full bg-current" />
        ) : (
          <LogIcon size={18} aria-hidden />
        )}
        {visible}
      </Link>
    </Button>
  )
}

/** Phones (under 900px): Today · Progress · Log · You along the bottom, Log in
 *  the middle (0a sign-off: middle is final), with a 2px marker that slides
 *  along the top edge to the current tab. */
export function TabBar({ active }: { active: Section | null }) {
  const row = useRef<HTMLDivElement>(null)
  const box = useMarker(row, active, 'x')
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-rule bg-ground pb-[env(safe-area-inset-bottom)] desk:hidden"
    >
      <div ref={row} className="relative grid h-16 grid-cols-[1fr_1fr_auto_1fr] items-center px-2">
        <Marker box={box} axis="x" className="top-0 left-0 h-0.5" />
        {TABS.slice(0, 2).map((tab) => (
          <TabLink key={tab.section} {...tab} active={active === tab.section} className={TAB_CLASS} />
        ))}
        {/* min-w keeps "Log" and "Ready" the same width, so the tabs either
            side don't shift when an estimate lands. */}
        <LogAction active={active === 'log'} place="bar" className="mx-1.5 min-w-[112px]" />
        <TabLink {...TABS[2]!} active={active === 'you'} className={TAB_CLASS} />
      </div>
    </nav>
  )
}

// The keyboard focus ring is the action colour (DESIGN.md, Inputs); without
// it these links fall back to index.css's older emerald ring.
const FOCUS = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

const TAB_CLASS = `flex min-h-[54px] flex-col items-center justify-center gap-0.5 text-[11.5px] tracking-[0.02em] [font-stretch:105%] transition-colors ${FOCUS}`

/** Desktop (900px and up): a 236px rail with the wordmark, the Log button and
 *  the tabs; the current tab has a 3px bar on its left that slides between
 *  them. */
export function RailNav({ active }: { active: Section | null }) {
  const list = useRef<HTMLDivElement>(null)
  const box = useMarker(list, active, 'y')
  return (
    <nav aria-label="Main" className="grid gap-[18px]">
      <LogAction active={active === 'log'} place="rail" className="w-full" />
      <div ref={list} className="relative grid gap-0.5">
        <Marker box={box} axis="y" className="top-0 left-0 w-[3px] py-2 [background-clip:content-box]" />
        {TABS.map((tab) => (
          <TabLink
            key={tab.section}
            {...tab}
            active={active === tab.section}
            className={`flex min-h-[46px] items-center gap-3 px-3 text-[15px] tracking-[0.02em] [font-stretch:105%] transition-colors ${FOCUS}`}
          />
        ))}
      </div>
    </nav>
  )
}
