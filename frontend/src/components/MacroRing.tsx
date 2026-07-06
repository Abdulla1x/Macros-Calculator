interface Props {
  label: string
  value: number
  goal: number
  unit: string
  color: string
}

export default function MacroRing({ label, value, goal, unit, color }: Props) {
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const progress = goal > 0 ? Math.min(value / goal, 1) : 0

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
      <span className="text-xs text-slate-500">{Math.round(progress * 100)}% of goal</span>
    </div>
  )
}
