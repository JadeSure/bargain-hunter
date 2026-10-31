import type { Metadata } from 'next'
import {
  bfVsBoxing,
  categorySummary,
  CATEGORIES,
  compare,
  coverage,
  discounts,
  forecast,
  headline,
  loadBf2026,
  money,
  topVoted,
  yearOf,
} from '@/lib/bf2026'

export const metadata: Metadata = {
  title: { absolute: '澳洲黑五 + 节礼日 2026' },
  robots: { index: false, follow: false },
}

const BF_DATE = '2026-11-27'
const MAX_PCT = 80
const CAT_COLOR: Record<string, string> = {
  数码电子: '#38bdf8',
  家电厨房: '#fbbf24',
  美妆个护: '#f472b6',
  户外运动: '#34d399',
  保健食品: '#a78bfa',
  礼品: '#fb923c',
  其他: '#a1a1aa',
}
const VERDICT_ORDER = ['黑五入手', '现在可买', '不用等黑五', '小心虚标']
const PRD_TARGET = { bfYears: 2, boxingYears: 1, nonBf: 3, retailers: 2 }

const sydneyToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Sydney' })
const dayNum = (iso: string) => Date.parse(iso + 'T00:00:00Z') / 86400000

function Src({ href, children }: { href: string; children: React.ReactNode }) {
  if (!href.startsWith('http')) return <>{children}</>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline decoration-zinc-600 underline-offset-2 hover:decoration-zinc-300">
      {children}
    </a>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10 min-w-0">
      <h2 className="mb-4 text-xl font-semibold text-zinc-50">{title}</h2>
      {children}
    </section>
  )
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="text-sm text-zinc-400">{label}</div>
      <div className="mt-1 text-xl font-semibold text-zinc-50">{value}</div>
      {sub && <div className="mt-1 text-sm text-zinc-400">{sub}</div>}
    </div>
  )
}

function CategoryLegend({ cats }: { cats: string[] }) {
  return (
    <p className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-400">
      {cats.map((c) => (
        <span key={c} className="flex items-center gap-1.5">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="5" fill={CAT_COLOR[c]} /></svg>
          {c}
        </span>
      ))}
    </p>
  )
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="whitespace-nowrap border-b border-zinc-700 px-3 py-2 text-left font-medium text-zinc-300">{children}</th>
)
const Td = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <td className={`border-b border-zinc-800 px-3 py-2 align-top ${className}`}>{children}</td>
)
const Scroll = ({ children }: { children: React.ReactNode }) => (
  <div className="overflow-x-auto rounded-lg border border-zinc-800">
    <table className="w-full min-w-[640px] text-sm text-zinc-200">{children}</table>
  </div>
)

export default async function Bf2026Page() {
  const { points, watch, calendar, prep, rules, facts, errors } = await loadBf2026()
  const ds = discounts(points)
  const cats = categorySummary(ds)
  const bds = discounts(points, '节礼日')
  const bdCats = categorySummary(bds)
  const stripCats = CATEGORIES.filter((c) => cats.some((x) => x.category === c) || bdCats.some((x) => x.category === c))
  const boxing = bfVsBoxing(points)
  const cmp = compare(points)
  const head = headline(ds, cmp)
  const fc = forecast(watch, points)
  const voted = topVoted(points)
  const cov = coverage(points, watch)
  const today = sydneyToday()
  const daysLeft = Math.round(dayNum(BF_DATE) - dayNum(today))
  const latestRetrieved = points.map((p) => p.retrieved_at).sort().at(-1) ?? ''
  const accc = facts.find((f) => f.id === 'accc_2025')
  const sortedDs = [...ds].sort((a, b) => b.pct - a.pct)
  const verdicts = [...new Set([...VERDICT_ORDER, ...fc.map((f) => f.watch.verdict)])]
  const phases = [...new Set(prep.map((p) => p.phase))]

  const winStart = dayNum('2026-11-01')
  const winEnd = dayNum('2027-01-02')
  const winLen = winEnd - winStart + 1
  const pctOf = (iso: string) => Math.min(100, Math.max(0, ((dayNum(iso) - winStart) / winLen) * 100))

  return (
    <main lang="zh-CN" className="mx-auto w-full max-w-5xl px-4 py-8 text-zinc-200 sm:px-6">
      <header>
        <h1 className="text-3xl font-bold text-zinc-50">澳洲黑五 + 节礼日 2026</h1>
        <p className="mt-2 text-sm text-zinc-400">
          数据截至 {latestRetrieved} · {points.length} 条价格 · {cov.files.length} 个来源文件
        </p>
      </header>

      {errors.length > 0 && (
        <div role="alert" className="mt-6 rounded-lg border border-amber-500 bg-amber-950 p-4 text-sm text-amber-100">
          <div className="font-semibold">有数据文件读取失败，已跳过：</div>
          <ul className="mt-1 list-disc pl-5">
            {errors.map((e) => <li key={e} className="break-words">{e}</li>)}
          </ul>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Tile label="黑五日期" value="11月27日 周五" sub={daysLeft >= 0 ? `还有 ${daysLeft} 天` : `已过 ${-daysLeft} 天`} />
        <Tile label="往年中位折扣" value={`${head.median_pct}%`} sub={`${head.n_deals} 条`} />
        <Tile label="最低价不在黑五" value={`${head.n_beaten} / ${head.n_compare}`} sub="有对比的商品里，别的时候更便宜的数量" />
        {accc && (
          <Tile label={accc.label} value={accc.value} />
        )}
      </div>

      <Section title="往年">
        <h3 className="mb-2 font-medium text-zinc-100">各品类折扣分布</h3>
        <p className="mb-3 text-sm text-zinc-400">每个点是一条折扣（横轴 0–{MAX_PCT}%），竖线是黑五中位数。已排除原价存疑的条目。</p>
        <CategoryLegend cats={stripCats} />
        <p className="mb-3 flex flex-wrap gap-x-4 text-sm text-zinc-400">
          <span className="flex items-center gap-1.5">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="#a1a1aa" /></svg>
            实心 = 黑五
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="none" stroke="#a1a1aa" strokeWidth="2.5" /></svg>
            空心 = 节礼日
          </span>
        </p>
        <div className="space-y-4">
          {stripCats.map((category) => {
            const mine = ds.filter((d) => d.point.category === category)
            const mineBd = bds.filter((d) => d.point.category === category)
            const bf = cats.find((x) => x.category === category)
            const bd = bdCats.find((x) => x.category === category)
            const mx = (pct: number) => (Math.min(pct, MAX_PCT) / MAX_PCT) * 392 + 4
            return (
              <div key={category}>
                <div className="flex flex-wrap justify-between gap-x-3 text-sm">
                  <span>{category}</span>
                  <span className="tabular-nums">
                    {bf ? `黑五中位 ${bf.median}%（${bf.n} 条）` : '黑五无数据'}
                    {bd ? ` · 节礼日中位 ${bd.median}%（${bd.n} 条）` : ''}
                  </span>
                </div>
                <svg viewBox="0 0 400 24" className="mt-1 w-full" role="img" aria-label={`${category} 折扣分布`}>
                  <line x1="0" x2="400" y1="12" y2="12" stroke="#3f3f46" />
                  {mine.map((d) => (
                    <circle key={d.point.id} cx={mx(d.pct)} cy="12" r="5" fill={CAT_COLOR[category]} fillOpacity="0.8" stroke="#09090b">
                      <title>{`黑五 · ${d.point.item} · ${d.point.date.slice(0, 4)} · ${d.pct}%`}</title>
                    </circle>
                  ))}
                  {mineBd.map((d) => (
                    <circle key={d.point.id} cx={mx(d.pct)} cy="12" r="4.5" fill="none" stroke={CAT_COLOR[category]} strokeWidth="2.5">
                      <title>{`节礼日 · ${d.point.item} · ${d.point.date} · ${d.pct}%`}</title>
                    </circle>
                  ))}
                  {bf && <line x1={mx(bf.median as number)} x2={mx(bf.median as number)} y1="1" y2="23" stroke="#fafafa" strokeWidth="2" />}
                </svg>
              </div>
            )
          })}
        </div>

        <h3 className="mb-2 mt-8 font-medium text-zinc-100">逐条折扣（从高到低）</h3>
        <CategoryLegend cats={cats.map((c) => c.category)} />
        <ul className="space-y-4">
          {sortedDs.map(({ point: p, pct }) => (
            <li key={p.id}>
              <div className="min-w-0 break-words text-sm">
                <Src href={p.source}>
                  {p.item} · {yearOf(p)} · {p.retailer || '—'} · {money(p.price)}（原价 {money(p.was_price as number)}）
                </Src>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-3 flex-1 rounded bg-zinc-800" title={`${p.item}：${pct}%`}>
                  <div className="h-3 rounded" style={{ width: `${Math.min(100, (pct / MAX_PCT) * 100)}%`, background: CAT_COLOR[p.category] ?? CAT_COLOR['其他'] }} />
                </div>
                <span className="w-10 shrink-0 text-right text-sm tabular-nums">{pct}%</span>
              </div>
            </li>
          ))}
        </ul>

        <h3 className="mb-2 mt-8 font-medium text-zinc-100">往年高票</h3>
        {voted.length === 0 ? (
          <p className="text-sm text-zinc-400">还没有票数数据，等 OzBargain 数据进来</p>
        ) : (
          voted.map((v) => (
            <div key={v.category} className="mb-3">
              <div className="text-sm text-zinc-400">{v.category}</div>
              <ul className="text-sm">
                {v.points.map((p) => (
                  <li key={p.id}>
                    <Src href={p.source}>{p.item} · {yearOf(p)} · {money(p.price)}</Src>（{p.votes} 票）
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </Section>

      <Section title="黑五是不是最便宜">
        <p className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-400">
          <span className="flex items-center gap-1.5">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="#f97316" /></svg>
            黑五最低价
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="none" stroke="#2dd4bf" strokeWidth="3" /></svg>
            其他时候的最低价
          </span>
          <span>横轴是同一行的价格</span>
        </p>
        <ul className="space-y-5">
          {cmp.map((c) => {
            const max = Math.max(c.bf.price, c.other?.price ?? 0) * 1.05
            const x = (v: number) => (v / max) * 380 + 10
            const bfLabel = `${c.bf.date.slice(0, 4)} 黑五${c.bf.retailer ? ` · ${c.bf.retailer}` : ''}`
            const o = c.other
            const otherLabel = !o
              ? ''
              : o.note
                ? o.conditions && !o.note.includes(o.conditions)
                  ? `${o.note}，${o.conditions}`
                  : o.note
                : [o.date, o.event, o.conditions, o.retailer].filter(Boolean).join(' · ')
            return (
              <li key={c.key}>
                <div className="font-medium text-zinc-100">{c.item}</div>
                <svg viewBox="0 0 400 20" className="mt-1 w-full" role="img" aria-label={`${c.item} 黑五与其他价格对比`}>
                  <line x1="0" x2="400" y1="10" y2="10" stroke="#3f3f46" />
                  {c.other && <line x1={x(c.other.price)} x2={x(c.bf.price)} y1="10" y2="10" stroke="#a1a1aa" strokeWidth="2" />}
                  {c.other && <circle cx={x(c.other.price)} cy="10" r="5" fill="none" stroke="#2dd4bf" strokeWidth="3"><title>{`其他 ${money(c.other.price)}`}</title></circle>}
                  <circle cx={x(c.bf.price)} cy="10" r="6" fill="#f97316"><title>{`黑五 ${money(c.bf.price)}`}</title></circle>
                </svg>
                <div className="mt-1 break-words text-sm">
                  <Src href={c.bf.source}>黑五 {money(c.bf.price)}（{bfLabel}）</Src>
                  {c.other ? (
                    <>
                      {' vs '}
                      <Src href={c.other.source}>其他 {money(c.other.price)}（{otherLabel}）</Src>
                      {c.beaten ? ` → 黑五贵 ${c.premium_pct}%` : ' → 黑五最低'}
                    </>
                  ) : (
                    ' → 黑五最低'
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </Section>

      <Section title="黑五 vs 节礼日">
        {boxing.length === 0 ? (
          <p className="text-sm text-zinc-400">还没有节礼日数据，等 OzBargain 节礼日数据进来（PRD 1b）</p>
        ) : (
          <>
            <p className="mb-3 text-sm">节礼日更便宜 {boxing.filter((r) => r.boxing_cheaper).length} / {boxing.length}</p>
            <ul className="space-y-3 text-sm">
              {boxing.map((r) => (
                <li key={r.key} className="break-words">
                  {r.item}：<Src href={r.bf.source}>黑五 {money(r.bf.price)}（{yearOf(r.bf)}{r.bf.retailer ? ` · ${r.bf.retailer}` : ''}）</Src>
                  {' vs '}
                  <Src href={r.bd.source}>
                    节礼日 {money(r.bd.price)}（{r.bd.date}{r.bd.retailer ? ` · ${r.bd.retailer}` : ''}{r.bd.conditions ? `，${r.bd.conditions}` : ''}）
                  </Src>
                  {r.boxing_cheaper ? ` → 等节礼日省 ${r.saving_pct}%` : (r.bd.price === r.bf.price ? ' → 一样' : ' → 黑五更便宜')}
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>

      <Section title="2026">
        <h3 className="mb-2 font-medium text-zinc-100">11月1日 – 1月2日</h3>
        <p className="mb-3 text-sm text-zinc-400">今天（悉尼）{today}{today < '2026-11-01' ? '，还没进入这段时间' : ''}</p>
        <ul className="space-y-3">
          {calendar.map((e) => {
            const visible = e.end >= '2026-11-01' && e.start <= '2027-01-02'
            const left = pctOf(e.start)
            const width = Math.max(1.5, pctOf(e.end) - left + 100 / winLen)
            return (
              <li key={e.id}>
                <div className="text-sm">
                  <Src href={e.source}>{e.event}</Src> · {e.date_label} · <span className="text-zinc-400">{e.status}</span>
                </div>
                <div className="relative mt-1 h-3 rounded bg-zinc-800" title={`${e.start} – ${e.end}`}>
                  {visible && <div className="absolute h-3 rounded bg-zinc-400" style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }} />}
                  {today >= '2026-11-01' && today <= '2027-01-02' && (
                    <div className="absolute -top-1 h-5 w-0.5 bg-orange-400" style={{ left: `${pctOf(today)}%` }} title={`今天 ${today}`} />
                  )}
                </div>
                {e.note && <div className="mt-1 text-xs text-zinc-400">{e.note}</div>}
              </li>
            )
          })}
        </ul>

        <h3 className="mb-2 mt-8 font-medium text-zinc-100">要不要等黑五</h3>
        {verdicts.map((v) => {
          const rows = fc.filter((f) => f.watch.verdict === v)
          if (!rows.length) return null
          return (
            <div key={v} className="mb-6">
              <div className="mb-2 text-sm font-medium text-zinc-100">{v}（{rows.length}）</div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {rows.map((f) => (
                  <div key={f.watch.key} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                    <div className="font-medium text-zinc-50">{f.watch.item}</div>
                    <div className="text-sm text-zinc-400">{f.watch.who}</div>
                    <div className="mt-2 break-words text-sm">
                      往年黑五 {f.range_text || '—'} · 今年已见{' '}
                      {f.seen26 ? (
                        <Src href={f.seen26.source}>
                          {money(f.seen26.price)}（{f.seen26.date}{f.seen26.conditions ? `，${f.seen26.conditions}` : ''}）
                        </Src>
                      ) : (
                        '—'
                      )}{' '}
                      · 提醒价 {f.target == null ? '—' : money(f.target)}
                    </div>
                    <div className="mt-2 break-words text-sm text-zinc-400">{f.watch.why}</div>
                    <code className="mt-3 inline-block select-all break-all rounded bg-zinc-800 px-1.5 py-0.5 text-sm">{f.kw}</code>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </Section>

      <Section title="现在要准备什么">
        {phases.map((phase) => (
          <div key={phase} className="mb-5">
            <div className="mb-2 text-sm font-medium text-zinc-100">{phase}</div>
            <ul className="space-y-2 text-sm">
              {prep.filter((p) => p.phase === phase).map((p) => (
                <li key={p.step}>
                  <span className="font-medium">{p.step}. <Src href={p.source}>{p.task}</Src></span>
                  <span className="text-zinc-400">（{p.by} 前）</span>
                  <div className="text-zinc-400">{p.detail}</div>
                </li>
              ))}
            </ul>
          </div>
        ))}

        <h3 className="mb-2 mt-6 font-medium text-zinc-100">寄回国规则</h3>
        <Scroll>
          <thead><tr><Th>事项</Th><Th>规则</Th><Th>状态</Th><Th>备注</Th></tr></thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <Td><Src href={r.source}>{r.topic}</Src></Td>
                <Td>{r.value}</Td>
                <Td>{r.status}</Td>
                <Td>{r.note}</Td>
              </tr>
            ))}
          </tbody>
        </Scroll>

        <h3 className="mb-2 mt-6 font-medium text-zinc-100">其他数据</h3>
        <ul className="space-y-1 text-sm">
          {facts.map((f) => (
            <li key={f.id}><Src href={f.source}>{f.label}</Src>：{f.value}</li>
          ))}
        </ul>
      </Section>

      <Section title="数据覆盖">
        <Scroll>
          <thead><tr><Th>文件</Th><Th>条数</Th><Th>黑五条数</Th><Th>年份</Th><Th>最新抓取</Th></tr></thead>
          <tbody>
            {cov.files.map((f) => (
              <tr key={f.file}><Td>{f.file}</Td><Td>{f.rows}</Td><Td>{f.bf_rows}</Td><Td>{f.years}</Td><Td>{f.latest}</Td></tr>
            ))}
          </tbody>
        </Scroll>
        <p className="mb-2 mt-6 text-sm text-zinc-400">目标：黑五年份 ≥{PRD_TARGET.bfYears}、节礼日年份 ≥{PRD_TARGET.boxingYears}、非黑五点 ≥{PRD_TARGET.nonBf}、2026 商家 ≥{PRD_TARGET.retailers}；不够的格子标「缺」。</p>
        <Scroll>
          <thead><tr><Th>商品</Th><Th>黑五年份数</Th><Th>节礼日年份数</Th><Th>非黑五点数</Th><Th>2026 商家数</Th></tr></thead>
          <tbody>
            {cov.keys.map((k) => (
              <tr key={k.key}>
                <Td>{k.item}</Td>
                <Td>{k.bf_years}{k.bf_years < PRD_TARGET.bfYears && <span className="ml-2 font-semibold text-amber-400">缺</span>}</Td>
                <Td>{k.boxing_years}{k.boxing_years < PRD_TARGET.boxingYears && <span className="ml-2 font-semibold text-amber-400">缺</span>}</Td>
                <Td>{k.non_bf}{k.non_bf < PRD_TARGET.nonBf && <span className="ml-2 font-semibold text-amber-400">缺</span>}</Td>
                <Td>{k.retailers_2026}{k.retailers_2026 < PRD_TARGET.retailers && <span className="ml-2 font-semibold text-amber-400">缺</span>}</Td>
              </tr>
            ))}
          </tbody>
        </Scroll>
      </Section>
    </main>
  )
}
