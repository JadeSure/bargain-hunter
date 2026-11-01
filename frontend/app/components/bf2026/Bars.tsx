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
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="break-words text-sm text-zinc-200">{r.label}</div>
          <div className="mt-1 flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <div
                className={`${thin ? 'h-2' : 'h-4'} min-w-[2px] rounded ${r.accent ? 'bg-sky-400' : 'bg-zinc-600'}`}
                style={{ width: `${(r.value / max) * 100}%` }}
              />
            </div>
            <span className="shrink-0 text-sm font-semibold tabular-nums text-zinc-50">{r.text}</span>
          </div>
        </li>
      ))}
    </ul>
  )
}
