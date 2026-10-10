import type { SVGProps } from 'react'

/** The app's icons: Phosphor (MIT), named by what they mean here, from
 *  DESIGN.md's Iconography mapping. Screens import from this file, never from
 *  Phosphor directly, so the mapping lives in one place.
 *
 *  Each comes from its own module: Phosphor's package does not mark itself
 *  side-effect free, so importing from its index could pull every icon (about
 *  1,500 of them) into the bundle.
 *
 *  Regular weight everywhere; `weight="fill"` only for the current tab. 22px by
 *  default, 18px in buttons and rows. An icon beside a text label is
 *  decorative: Phosphor's components have no accessible name unless given an
 *  `aria-label`, so pass `aria-hidden` next to text. */
export { CalendarCheckIcon as TodayIcon } from '@phosphor-icons/react/dist/csr/CalendarCheck'
export { ChartLineIcon as ProgressIcon } from '@phosphor-icons/react/dist/csr/ChartLine'
export { UserIcon as YouIcon } from '@phosphor-icons/react/dist/csr/User'
export { PlusIcon as LogIcon } from '@phosphor-icons/react/dist/csr/Plus'
export { DropIcon as WaterIcon } from '@phosphor-icons/react/dist/csr/Drop'
export { PillIcon as SupplementsIcon } from '@phosphor-icons/react/dist/csr/Pill'
export { MicrophoneIcon as VoiceIcon } from '@phosphor-icons/react/dist/csr/Microphone'
export { CameraIcon as PhotoIcon } from '@phosphor-icons/react/dist/csr/Camera'
export { BookOpenIcon as SavedFoodsIcon } from '@phosphor-icons/react/dist/csr/BookOpen'
export { PencilSimpleIcon as EditIcon } from '@phosphor-icons/react/dist/csr/PencilSimple'
export { CopyIcon as LogAgainIcon } from '@phosphor-icons/react/dist/csr/Copy'
export { ShareNetworkIcon as ShareIcon } from '@phosphor-icons/react/dist/csr/ShareNetwork'
export { StarIcon as KeepIcon } from '@phosphor-icons/react/dist/csr/Star'
export { TrashIcon as DeleteIcon } from '@phosphor-icons/react/dist/csr/Trash'
export { CaretLeftIcon as BackIcon } from '@phosphor-icons/react/dist/csr/CaretLeft'
export { CaretRightIcon as NextIcon } from '@phosphor-icons/react/dist/csr/CaretRight'
export { XIcon as CloseIcon } from '@phosphor-icons/react/dist/csr/X'
export { CheckIcon as DoneIcon } from '@phosphor-icons/react/dist/csr/Check'
// Not in DESIGN.md's mapping: the AI box's collapsed row, when editing a meal.
export { SparkleIcon as EstimateIcon } from '@phosphor-icons/react/dist/csr/Sparkle'
// Not in DESIGN.md's mapping either: the Log panel's search over saved and
// recent meals.
export { MagnifyingGlassIcon as SearchIcon } from '@phosphor-icons/react/dist/csr/MagnifyingGlass'
// Not in DESIGN.md's mapping either: the caret on a "How is this worked out?"
// disclosure, turned over while it is open.
export { CaretDownIcon as ExpandIcon } from '@phosphor-icons/react/dist/csr/CaretDown'
// Not in DESIGN.md's mapping either: the steps tracker, which replaced its 👟.
export { FootprintsIcon as StepsIcon } from '@phosphor-icons/react/dist/csr/Footprints'

/** The weigh-in scale. Phosphor has no bathroom scale, so this one is drawn on
 *  Phosphor's 256 grid at its 16-unit line weight (DESIGN.md, Iconography), to
 *  sit beside the others. Takes the same `size` prop as a Phosphor icon. */
export function WeighInIcon({ size = 22, ...props }: SVGProps<SVGSVGElement> & { size?: number | string }) {
  return (
    <svg
      viewBox="0 0 256 256"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={16}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect x="40" y="40" width="176" height="176" rx="40" />
      <path d="M84 112a52 52 0 0 1 88 0" />
      <path d="M128 136l16-28" />
    </svg>
  )
}
