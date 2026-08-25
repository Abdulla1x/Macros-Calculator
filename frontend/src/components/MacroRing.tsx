interface Props {
  label: string
  value: number
  goal: number
  unit: string
  color: string
  /** One line under the percentage, for anything that explains the goal this
   *  ring is drawn against — a plan moving it, or the fact that we could not
   *  check whether one does. Absent on an ordinary day. */
  caption?: string
}

export default function MacroRing({ label, value, goal, unit, color, caption }: Props) {
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const ratio = goal > 0 ? value / goal : 0
  // The ARC is capped; the NUMBER is not. A ring cannot draw past full without
  // becoming unreadable, but printing "100% of goal" for a 2,400 kcal day
  // against a 2,000 kcal goal is the display refusing to admit there is an
  // overage at all -- and this app now offers to spread one, which it cannot
  // sensibly do next to a figure that says nothing happened.
  const progress = Math.min(ratio, 1)

  return (
    <div className="flex flex-col items-center rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="relative h-32 w-32">
        <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
          <circle cx="64" cy="64" r={radius} fill="none" stroke="#1e293b" strokeWidth="11" />
          <circle
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="11"
            strokeLinecap="round"
            strokeDasharray={`${circumference * progress} ${circumference}`}
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold">{Math.round(value)}</span>
          <span className="text-xs text-slate-500">/ {Math.round(goal)} {unit}</span>
        </div>
      </div>
      <span className="mt-2 text-sm font-medium text-slate-300">{label}</span>
      <span className="text-xs text-slate-500">{Math.round(ratio * 100)}% of goal</span>
      {caption && (
        <span className="mt-1 text-center text-[11px] leading-tight text-slate-400">
          {caption}
        </span>
      )}
    </div>
  )
}
