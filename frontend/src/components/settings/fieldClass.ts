// The text-input class string shared by the Settings page and the sections
// split out of it.
//
// Hoisted here rather than duplicated because three files now type it: the
// page's own Body profile fields, AccountSection's password and delete-
// confirmation boxes, and HeightField's centimetre and foot/inch pair. Water
// and Steps deliberately do NOT use it -- their inputs carry a per-tracker
// focus hue (sky, violet) that this string would flatten.
//
// `text-base sm:text-sm` is load-bearing and not a typo: anything under 16px
// makes mobile Safari and Chrome zoom the viewport on focus, so the small
// size is applied from the `sm` breakpoint up, where there is no touch
// keyboard to trigger it.
//
// Temporary. Phase 18 replaces every use of this with a ui/TextInput taking an
// `accent` prop, at which point this file is deleted rather than edited -- the
// per-tracker hues above are exactly the variants that prop exists for.
export const fieldClass =
  'w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-base sm:text-sm focus:border-emerald-500'
