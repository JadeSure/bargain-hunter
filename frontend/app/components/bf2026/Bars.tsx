export interface BarRow {
  label: string
  value: number
  text: string
  accent?: boolean
}

// Horizontal bars: label on top, bar below, the number printed at the bar end. No axes, no legend.
export default function Bars({ rows, thin = false }: { rows: BarRow[]; thin?: boolean }) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1
  return (
    <ul className={thin ? 'space-y-2' : 'space-y-4'}>
      {rows.map((r) => (
        <li key={r.label}>
          <div className={`break-words text-zinc-300 ${thin ? 'text-xs' : 'text-sm'}`}>{r.label}</div>
          <div className="bf-barrow">
            <div className={thin ? 'bf-track-thin' : 'bf-track'}>
              <div
                className={`bf-fill ${r.accent ? 'from-sky-400 to-indigo-500' : 'from-zinc-600 to-zinc-500'}`}
                style={{ width: `${(r.value / max) * 100}%` }}
              />
            </div>
            <span className={`shrink-0 font-bold tabular-nums text-zinc-50 ${thin ? 'text-sm' : 'text-base'}`}>{r.text}</span>
          </div>
        </li>
      ))}
    </ul>
  )
}
