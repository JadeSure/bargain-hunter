'use client'

const HOT_VOTES = 50

// days: flat [count, hotCount] pairs, one pair per day offset from `lo` to `hi`.
export interface TimingSeries {
  year: number
  total: number
  days: number[]
}

export default function Timing({ title, lo, hi, anchorLabel, series }: { title: string; lo: number; hi: number; anchorLabel: string; series: TimingSeries[] }) {
  const span = hi - lo + 1
  const w = 400 / span
  const max = Math.max(1, ...series.flatMap((s) => s.days.filter((_, i) => i % 2 === 0)))
  const offLabel = (off: number) => (off === 0 ? anchorLabel : off < 0 ? `前${-off}天` : `后${off}天`)
  const ticks = [lo, Math.round(lo / 2), 0, hi].filter((v, i, a) => a.indexOf(v) === i)
  return (
    <div className="mb-8">
      <h3 className="mb-2 font-medium text-zinc-100">{title}</h3>
      {series.length === 0 ? (
        <p className="text-sm text-zinc-400">没有带具体日期的数据。</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {series.map((s) => {
            const days = Array.from({ length: span }, (_, i) => ({ off: lo + i, n: s.days[i * 2], hot: s.days[i * 2 + 1] }))
            const hotTotal = days.reduce((a, d) => a + d.hot, 0)
            const peaks = days.filter((d) => d.hot > 0).sort((a, b) => b.hot - a.hot).slice(0, 3).map((d) => offLabel(d.off))
            return (
              <div key={s.year}>
                <div className="text-sm">
                  {s.year} 季 · 共 {s.total} 条 · 票数 ≥{HOT_VOTES} 的 {hotTotal} 条{peaks.length > 0 && `，集中在 ${peaks.join('、')}`}
                </div>
                <svg viewBox="0 0 400 92" className="mt-1 w-full" role="img" aria-label={`${s.year} 季每天新出的好价数量`}>
                  <line x1="0" x2="400" y1="72" y2="72" stroke="#52525b" />
                  <line x1={(0 - lo) * w + w / 2} x2={(0 - lo) * w + w / 2} y1="14" y2="72" stroke="#f97316" strokeDasharray="3 2" />
                  <path
                    fill="#a1a1aa"
                    d={days.filter((d) => d.n > 0).map((d) => {
                      const h = (d.n / max) * 54
                      return `M${((d.off - lo) * w + 1).toFixed(1)} 72v${(-h).toFixed(1)}h${Math.max(1, w - 2).toFixed(1)}v${h.toFixed(1)}z`
                    }).join('')}
                  >
                    <title>{`${s.year} 季每天新出的好价数量。最多的几天：${days.filter((d) => d.n > 0).sort((a, b) => b.n - a.n).slice(0, 5).map((d) => `${offLabel(d.off)} ${d.n} 条`).join('、')}`}</title>
                  </path>
                  <g fill="none" stroke="#2dd4bf" strokeWidth="2">
                    {days.map((d, i) => d.hot > 0 && <circle key={d.off} cx={i * w + w / 2} cy="7" r="4" />)}
                  </g>
                  {ticks.map((t) => (
                    <text key={t} x={(t - lo) * w + w / 2} y="87" textAnchor="middle" fontSize="9" fill="#a1a1aa">{offLabel(t)}</text>
                  ))}
                </svg>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
