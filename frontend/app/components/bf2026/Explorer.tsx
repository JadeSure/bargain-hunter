'use client'

import { useEffect, useMemo, useState } from 'react'
import { CATEGORIES, MAX_PCT, money, pairPasses, suspectCount } from '@/lib/bf2026-derive'
import type { BoxingPair, ComparePair, Filters, Side } from '@/lib/bf2026-derive'
import { CAT_COLOR, TABLE_CLASS, unpackUrl, verifyLabel } from './shared'
import type { DealTuple, ExcludedTuple, PairTuple, SideTuple } from './shared'

interface DealRow {
  item: string
  retailer: string
  source: string
  file: string
  category: string
  year: number
  event: 'bf' | 'bd'
  price: number
  was: number
  pct: number
  votes: number | null
}

interface Props {
  deals: DealTuple[]
  excluded: ExcludedTuple[]
  compare: PairTuple[]
  boxing: PairTuple[]
  files: string[]
  years: number[]
}

const PAGE = 10
const BIN = 5
const BINS = MAX_PCT / BIN
const VOTE_CHOICES = [0, 20, 50, 100, 200]
const DEFAULT_CATS = CATEGORIES.filter((c) => c !== '其他')

function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2)
}

function Src({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={unpackUrl(href)} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
      {children}
    </a>
  )
}

function Histogram({ category, bf, bd }: { category: string; bf: DealRow[]; bd: DealRow[] }) {
  const bin = (r: DealRow) => Math.min(BINS - 1, Math.max(0, Math.floor(r.pct / BIN)))
  const count = (rows: DealRow[]) => {
    const c = Array<number>(BINS).fill(0)
    for (const r of rows) c[bin(r)]++
    return c
  }
  const cb = count(bf)
  const cd = count(bd)
  const max = Math.max(1, ...cb, ...cd)
  const w = 400 / BINS
  const x = (pct: number) => (pct / MAX_PCT) * 400
  const color = CAT_COLOR[category]
  const med = (rows: DealRow[]) => (rows.length >= 5 ? median(rows.map((r) => r.pct)) : null)
  const mb = med(bf)
  const md = med(bd)
  return (
    <div>
      <div className="flex flex-wrap justify-between gap-x-3 text-sm">
        <span>{category}</span>
        <span className="tabular-nums">
          黑五 {mb != null ? `中位 ${mb}%` : '样本不足'}（{bf.length} 条）
          {bd.length > 0 && ` · 节礼日 ${md != null ? `中位 ${md}%` : '样本不足'}（${bd.length} 条）`}
        </span>
      </div>
      <svg viewBox="0 0 400 66" className="mt-1 w-full" role="img" aria-label={`${category} 折扣分布，实心为黑五，空心为节礼日`}>
        <line x1="0" x2="400" y1="33" y2="33" stroke="#52525b" />
        <path fill={color} fillOpacity="0.85" d={cb.map((n, i) => (n > 0 ? `M${(i * w + 1).toFixed(1)} 31v${(-(n / max) * 29).toFixed(1)}h${(w - 2).toFixed(1)}v${((n / max) * 29).toFixed(1)}z` : '')).join('')}>
          <title>{`黑五（实心）：${cb.map((n, i) => (n > 0 ? `${i * BIN}–${(i + 1) * BIN}% ${n} 条` : '')).filter(Boolean).join('、') || '无'}`}</title>
        </path>
        <path fill="none" stroke={color} strokeWidth="2" d={cd.map((n, i) => (n > 0 ? `M${(i * w + 2).toFixed(1)} 35v${((n / max) * 29).toFixed(1)}h${(w - 4).toFixed(1)}v${(-(n / max) * 29).toFixed(1)}z` : '')).join('')}>
          <title>{`节礼日（空心）：${cd.map((n, i) => (n > 0 ? `${i * BIN}–${(i + 1) * BIN}% ${n} 条` : '')).filter(Boolean).join('、') || '无'}`}</title>
        </path>
        {mb != null && <line x1={x(mb)} x2={x(mb)} y1="0" y2="31" stroke="#fafafa" strokeWidth="2" />}
        {md != null && <line x1={x(md)} x2={x(md)} y1="35" y2="66" stroke="#fafafa" strokeWidth="2" strokeDasharray="3 2" />}
      </svg>
    </div>
  )
}

const Th = ({ children }: { children: React.ReactNode }) => <th>{children}</th>
const Td = ({ children, className }: { children: React.ReactNode; className?: string }) => <td className={className}>{children}</td>

function MoreButton({ shown, total, onMore }: { shown: number; total: number; onMore: () => void }) {
  if (shown >= total) return null
  return (
    <button type="button" onClick={onMore} className="mt-2 rounded border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800">
      展开更多（还有 {total - shown} 条）
    </button>
  )
}

export default function Explorer({ deals: dealTuples, excluded: excludedTuples, compare: cmpTuples, boxing: boxTuples, files, years }: Props) {
  const deals = useMemo<DealRow[]>(
    () =>
      dealTuples.map((t) => ({
        item: t[0], retailer: t[1], source: t[2], file: files[t[3]], category: CATEGORIES[t[4]], year: t[5],
        event: t[6] === 0 ? 'bf' : 'bd', price: t[7], was: t[8], pct: t[9], votes: t[10] < 0 ? null : t[10],
      })),
    [dealTuples, files],
  )
  const excluded = excludedTuples
  const side = (t: SideTuple): Side => ({
    item: t[0], price: t[1], date: t[2], event: t[3], retailer: t[4], file: files[t[5]], votes: t[6] < 0 ? null : t[6], source: t[7], note: t[8],
  })
  const compare = useMemo<ComparePair[]>(
    () =>
      cmpTuples.map((t) => {
        const bf = side(t[4])
        const other = side(t[5])
        return { key: t[0], category: CATEGORIES[t[1]], year: t[2], comparable: t[3] === 1, bf, other, beaten: other.price < bf.price, premium_pct: Math.round((bf.price / other.price - 1) * 100) }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cmpTuples, files],
  )
  const boxing = useMemo<BoxingPair[]>(
    () =>
      boxTuples.map((t) => {
        const bf = side(t[4])
        const bd = side(t[5])
        return { key: t[0], category: CATEGORIES[t[1]], year: t[2], comparable: t[3] === 1, bf, bd, boxing_cheaper: bd.price < bf.price, saving_pct: Math.round((1 - bd.price / bf.price) * 100) }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [boxTuples, files],
  )
  const [cats, setCats] = useState<string[]>([...DEFAULT_CATS])
  const [year, setYear] = useState<number | null>(null)
  const [file, setFile] = useState<string | null>(null)
  const [minVotes, setMinVotes] = useState(20)
  const [shown, setShown] = useState<Record<string, number>>({})

  // Filter state lives in the URL query so a filtered view can be bookmarked.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search)
    const c = q.get('c')
    if (c != null) setCats(c.split(',').filter((x) => (CATEGORIES as readonly string[]).includes(x)))
    const y = Number(q.get('y'))
    if (y) setYear(y)
    setFile(q.get('src'))
    const v = q.get('v')
    if (v != null && !Number.isNaN(Number(v))) setMinVotes(Number(v))
  }, [])

  const sync = (next: { cats: string[]; year: number | null; file: string | null; minVotes: number }) => {
    const q = new URLSearchParams()
    if (next.cats.join() !== DEFAULT_CATS.join()) q.set('c', next.cats.join(','))
    if (next.year != null) q.set('y', String(next.year))
    if (next.file) q.set('src', next.file)
    if (next.minVotes !== 20) q.set('v', String(next.minVotes))
    const s = q.toString()
    window.history.replaceState(null, '', window.location.pathname + (s ? `?${s}` : ''))
  }
  const update = (patch: Partial<{ cats: string[]; year: number | null; file: string | null; minVotes: number }>) => {
    const next = { cats, year, file, minVotes, ...patch }
    setCats(next.cats)
    setYear(next.year)
    setFile(next.file)
    setMinVotes(next.minVotes)
    sync(next)
  }

  const f: Filters = { cats, year, file, minVotes }
  const rows = deals.filter((r) => pairPasses({ category: r.category, year: r.year, sides: [r] }, f))
  const cmpAll = compare.filter((p) => pairPasses({ category: p.category, year: p.year, sides: [p.bf, p.other] }, f))
  const cmp = cmpAll.filter((p) => p.comparable)
  const boxAll = boxing.filter((p) => pairPasses({ category: p.category, year: p.year, sides: [p.bf, p.bd] }, f))
  const box = boxAll.filter((p) => p.comparable)
  const more = (key: string) => setShown((s) => ({ ...s, [key]: (s[key] ?? PAGE) + PAGE }))
  const activeCats = CATEGORIES.filter((c) => cats.includes(c) && rows.some((r) => r.category === c))

  return (
    <>
      <div className="mt-8 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="mb-2 text-sm font-medium text-zinc-100">筛选（只影响下面的图表、榜单和对比；上面的数字卡是全量）</div>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((c) => {
            const on = cats.includes(c)
            return (
              <button
                key={c}
                type="button"
                aria-pressed={on}
                onClick={() => update({ cats: on ? cats.filter((x) => x !== c) : [...cats, c] })}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${on ? 'border-zinc-400 bg-zinc-800 text-zinc-50' : 'border-zinc-700 text-zinc-400'}`}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill={CAT_COLOR[c]} /></svg>
                {c}{on ? ' ✓' : ''}
              </button>
            )
          })}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            年份
            <select value={year ?? ''} onChange={(e) => update({ year: e.target.value ? Number(e.target.value) : null })} className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1">
              <option value="">全部</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            来源文件
            <select value={file ?? ''} onChange={(e) => update({ file: e.target.value || null })} className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1">
              <option value="">全部</option>
              {files.map((x) => <option key={x} value={x}>{x}（{verifyLabel(x)}）</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            OzBargain 最低票数
            <select value={minVotes} onChange={(e) => update({ minVotes: Number(e.target.value) })} className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1">
              {VOTE_CHOICES.map((v) => <option key={v} value={v}>{v === 0 ? '不限' : `≥ ${v} 票`}</option>)}
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-zinc-400">其他来源没有票数，不受票数门槛影响。「其他」品类默认不选。</p>
      </div>

      <section className="mt-10 min-w-0">
        <h2 className="mb-4 text-xl font-semibold text-zinc-50">往年</h2>
        <h3 className="mb-2 font-medium text-zinc-100">各品类折扣分布</h3>
        <p className="mb-3 text-sm text-zinc-400">
          每格 {BIN}%，横轴 0–{MAX_PCT}%。上半实心 = 黑五，下半空心 = 节礼日，竖线 = 中位数（样本少于 5 条不画）。
          当前 {rows.length} 条。已排除 {excluded.length} 条异常（带条件、折扣超过 {MAX_PCT}%、价格低于 $5）。
        </p>
        <details className="mb-4 text-sm">
          <summary className="cursor-pointer text-zinc-300">看被排除的 {excluded.length} 条</summary>
          <ul className="mt-2 space-y-1 text-zinc-400">
            {excluded.map((e, i) => (
              <li key={i} className="break-words">
                <Src href={e[5]}>{e[0]}</Src> · {money(e[1])}（原价 {money(e[2])}，{e[3]}%）· {e[4]}
              </li>
            ))}
          </ul>
        </details>
        {activeCats.length === 0 ? (
          <p className="text-sm text-zinc-400">当前筛选下没有数据。</p>
        ) : (
          <div className="space-y-5">
            {activeCats.map((c) => (
              <Histogram key={c} category={c} bf={rows.filter((r) => r.category === c && r.event === 'bf')} bd={rows.filter((r) => r.category === c && r.event === 'bd')} />
            ))}
          </div>
        )}

        <h3 className="mb-2 mt-8 font-medium text-zinc-100">往年好价榜</h3>
        <p className="mb-3 text-sm text-zinc-400">每个品类先按票数（只有 OzBargain 有票数），没有票数的再按折扣排。</p>
        {activeCats.map((c) => {
          const list = rows
            .filter((r) => r.category === c)
            .sort((a, b) => {
              if ((a.votes != null) !== (b.votes != null)) return a.votes != null ? -1 : 1
              if (a.votes != null && b.votes != null && a.votes !== b.votes) return b.votes - a.votes
              return b.pct - a.pct
            })
          const n = shown[c] ?? PAGE
          return (
            <div key={c} className="mb-6">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-100">
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill={CAT_COLOR[c]} /></svg>
                {c}（{list.length} 条）
              </div>
              <div className="overflow-x-auto rounded-lg border border-zinc-800">
                <table className={TABLE_CLASS} style={{ minWidth: 720 }}>
                  <thead><tr><Th>商品</Th><Th>年份</Th><Th>商家</Th><Th>到手价</Th><Th>原价</Th><Th>折扣</Th><Th>票数</Th></tr></thead>
                  <tbody>
                    {list.slice(0, n).map((r, i) => (
                      <tr key={i}>
                        <Td className="max-w-[18rem] break-words"><Src href={r.source}>{r.item}</Src>{r.event === 'bd' && <span className="ml-1 text-zinc-400">（节礼日）</span>}</Td>
                        <Td>{r.year}</Td>
                        <Td>{r.retailer || '—'}</Td>
                        <Td className="whitespace-nowrap">{money(r.price)}</Td>
                        <Td className="whitespace-nowrap">{money(r.was)}</Td>
                        <Td className="whitespace-nowrap">{r.pct}%</Td>
                        <Td>{r.votes ?? '—'}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <MoreButton shown={n} total={list.length} onMore={() => more(c)} />
            </div>
          )
        })}
      </section>

      <section className="mt-10 min-w-0">
        <h2 className="mb-4 text-xl font-semibold text-zinc-50">黑五是不是最便宜</h2>
        <p className="mb-2 text-sm text-zinc-400">
          黑五季 Y 的最低价，只和购物年 Y（Y-06-01 到 Y+1-05-31）里非黑五的最低价比；都不含带条件的价。筛选作用在这两条最低价上。
        </p>
        <p className="mb-4 text-sm">
          当前筛选下：最低价不在黑五 <b>{cmp.filter((p) => p.beaten).length} / {cmp.length}</b>（样本 {cmp.length} 个商品·年）
          {suspectCount(cmpAll) > 0 && <span className="text-zinc-400"> · 另有 {suspectCount(cmpAll)} 个商品编号存疑，未比较</span>}
        </p>
        <p className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-400">
          <span className="flex items-center gap-1.5"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="#f97316" /></svg>黑五最低价</span>
          <span className="flex items-center gap-1.5"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="none" stroke="#2dd4bf" strokeWidth="3" /></svg>同购物年其他时候的最低价</span>
        </p>
        <ul className="space-y-5">
          {cmp.slice(0, shown.cmp ?? PAGE).map((c) => {
            const max = Math.max(c.bf.price, c.other.price) * 1.05
            const x = (v: number) => (v / max) * 380 + 10
            const otherLabel = c.other.note || [c.other.date, c.other.event, c.other.retailer].filter(Boolean).join(' · ')
            return (
              <li key={`${c.key}-${c.year}`}>
                <div className="font-medium text-zinc-100">{c.bf.item}（{c.year}）</div>
                <svg viewBox="0 0 400 20" className="mt-1 w-full" role="img" aria-label={`${c.bf.item} 黑五与其他价格对比`}>
                  <line x1="0" x2="400" y1="10" y2="10" stroke="#3f3f46" />
                  <line x1={x(c.other.price)} x2={x(c.bf.price)} y1="10" y2="10" stroke="#a1a1aa" strokeWidth="2" />
                  <circle cx={x(c.other.price)} cy="10" r="5" fill="none" stroke="#2dd4bf" strokeWidth="3"><title>{`其他 ${money(c.other.price)}`}</title></circle>
                  <circle cx={x(c.bf.price)} cy="10" r="6" fill="#f97316"><title>{`黑五 ${money(c.bf.price)}`}</title></circle>
                </svg>
                <div className="mt-1 break-words text-sm">
                  <Src href={c.bf.source}>黑五 {money(c.bf.price)}（{c.year} 黑五{c.bf.retailer ? ` · ${c.bf.retailer}` : ''}）</Src>
                  {' vs '}
                  <Src href={c.other.source}>其他 {money(c.other.price)}（{otherLabel}）</Src>
                  {c.premium_pct === 0 ? ' → 一样' : c.beaten ? ` → 黑五贵 ${c.premium_pct}%` : ' → 黑五最低'}
                </div>
              </li>
            )
          })}
        </ul>
        <MoreButton shown={shown.cmp ?? PAGE} total={cmp.length} onMore={() => more('cmp')} />
      </section>

      <section className="mt-10 min-w-0">
        <h2 className="mb-4 text-xl font-semibold text-zinc-50">黑五 vs 节礼日</h2>
        {box.length === 0 ? (
          <p className="text-sm text-zinc-400">当前筛选下没有可比的商品。</p>
        ) : (
          <>
            <p className="mb-3 text-sm">
              当前筛选下：节礼日更便宜 <b>{box.filter((r) => r.boxing_cheaper).length} / {box.length}</b>（样本 {box.length} 个商品·年）
              {suspectCount(boxAll) > 0 && <span className="text-zinc-400"> · 另有 {suspectCount(boxAll)} 个商品编号存疑，未比较</span>}
            </p>
            <ul className="space-y-3 text-sm">
              {box.slice(0, shown.box ?? PAGE).map((r) => (
                <li key={`${r.key}-${r.year}`} className="break-words">
                  {r.bf.item}：<Src href={r.bf.source}>黑五 {money(r.bf.price)}（{r.year}{r.bf.retailer ? ` · ${r.bf.retailer}` : ''}）</Src>
                  {' vs '}
                  <Src href={r.bd.source}>节礼日 {money(r.bd.price)}（{r.bd.date}{r.bd.retailer ? ` · ${r.bd.retailer}` : ''}）</Src>
                  {r.saving_pct === 0 ? ' → 一样' : r.boxing_cheaper ? ` → 等节礼日省 ${r.saving_pct}%` : ' → 黑五更便宜'}
                </li>
              ))}
            </ul>
            <MoreButton shown={shown.box ?? PAGE} total={box.length} onMore={() => more('box')} />
          </>
        )}
      </section>
    </>
  )
}
