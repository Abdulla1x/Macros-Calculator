/** Wordmark D (DESIGN.md, Brand): the name in the label face, the segmented
 *  gauge as its rule (nine lit, three unlit, the plan-coloured target tick),
 *  and a nutrition-label line, "Serving size ... 1 habit".
 *
 *  Built from HTML rather than DESIGN.md's SVG: the SVG sets the name in
 *  <text>, which renders in whatever font is installed until the mark is
 *  outlined, while this uses the self-hosted Libre Franklin, follows the
 *  theme's ink and plan colours, and stays sharp at any size. The name is
 *  real text; the gauge and the serving line are decoration. */
export default function Wordmark({ className = '' }: { className?: string }) {
  return (
    <div className={`inline-grid font-label text-ink ${className}`}>
      <span className="text-[28px] leading-none font-black tracking-[-0.035em]">Trackaholic</span>
      <span aria-hidden="true" className="mt-[5px] mb-[3px] grid h-1.5 grid-cols-[repeat(12,1fr)_3px] gap-[2px]">
        {Array.from({ length: 12 }, (_, i) => (
          <i key={i} className={i < 9 ? 'bg-ink' : 'bg-ink/20'} />
        ))}
        <i className="bg-plan" />
      </span>
      <span aria-hidden="true" className="flex justify-between gap-3 border-t border-ink pt-0.5 text-xs">
        <span>Serving size</span>
        <b className="font-extrabold">1 habit</b>
      </span>
    </div>
  )
}
