'use client'

import { useEffect, useState } from 'react'
import {
  ALL_FILES,
  ALL_YEARS,
  BD_EVENT,
  BF_EVENT,
  BOARD_LIMIT,
  CATEGORIES,
  MIN_SAMPLE,
  NO_VOTES,
  OTHER_CAT,
  VOTE_OPTIONS,
  board,
  compareShoppingYear,
  countsOf,
  defaultFilter,
  depthOf,
  filterRows,
  keepsCat,
  median,
  money,
  passesVotes,
  readFilter,
  writeFilter,
  type BoardRow,
  type CountCell,
  type ExcludedRow,
  type Filter,
  type SeasonRow,
} from '@/lib/bf2026-derive'
import Bars from './Bars'
import { LazyDetails } from './Lazy'
import Thumb from './Thumb'
import { Evidence, Section, SubHead, Takeaway } from './Ui'
import { TABLE_CLASS, unpackUrl } from './shared'

// [category, item, 2024 price, 2025 price, trend, votes, packed source, key, image]
export type RecRow = [number, string, number, number, string, number, string, string, string]

export interface ExplorerData {
  rows: BoardRow[]
  cells: CountCell[]
  seasons: SeasonRow[]
  excluded: ExcludedRow[]
  rec: RecRow[]
  brands: { name: string; n: number }[]
  files: string[]
  years: number[]
}

const TREND_CHIP: Record<string, string> = { 降价中: 'bf-emerald', 涨价了: 'bf-rose', 差不多: 'bf-zinc' }
const TREND_ARROW: Record<string, string> = { 降价中: '↓', 涨价了: '↑', 差不多: '→' }

const Link = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="bf-link">{children}</a>
)

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={on ? 'bf-fchip-on' : 'bf-fchip'}>
      {children}
    </button>
  )
}

export default function Explorer({ data }: { data: ExplorerData }) {
  const { rows, cells, seasons, excluded, rec, brands, files, years } = data
  const [f, setF] = useState<Filter>(defaultFilter)

  // The prerendered HTML is the default view; a bookmarked query is applied once on mount.
  useEffect(() => {
    setF(readFilter(window.location.search, files))
  }, [files])

  const set = (next: Filter) => {
    setF(next)
    const qs = writeFilter(next, files)
    window.history.replaceState(null, '', qs || window.location.pathname)
  }
  const toggleCat = (i: number) => set({ ...f, cats: f.cats.includes(i) ? f.cats.filter((x) => x !== i) : [...f.cats, i] })

  const blocks = board(rows, f)
  const depth = depthOf(rows, f)
  const ranked = [...depth].filter((d) => d.median != null).sort((a, b) => (b.median as number) - (a.median as number))
  const counts = countsOf(cells, f)
  const sy = compareShoppingYear(seasons, f)
  const shown = filterRows(rows, f)
  const medianOf = (event: number) => {
    const pcts = shown.filter((r) => r[1] === event).map((r) => r[5])
    return { n: pcts.length, median: pcts.length >= MIN_SAMPLE ? median(pcts) : null }
  }
  const bfMed = medianOf(BF_EVENT)
  const bdMed = medianOf(BD_EVENT)
  const recShown = rec.filter((r) => keepsCat(r[0], f) && passesVotes(r[5], f.minVotes))
  const excludedShown = excluded.filter((r) => keepsCat(r[0], f) && (f.year === ALL_YEARS || r[1] === f.year))
  const yearText = f.year === ALL_YEARS ? (years.length ? `${years[years.length - 1]}–${years[0]} 年` : '全部年份') : `${f.year} 年`
  const scope = `${f.cats.length ? f.cats.map((i) => CATEGORIES[i]).join('、') : '全部品类'}${f.other ? ' + 其他' : ''} · ${yearText} · ${f.file === ALL_FILES ? '全部来源' : files[f.file]} · 票数 ≥ ${f.minVotes}`

  return (
    <>
      <Section id="explore" emoji="🔎" title="往年数据：筛选着看">
        <div className="space-y-3">
          <div className="bf-frow">
            <span className="bf-flabel">品类</span>
            {CATEGORIES.slice(0, OTHER_CAT).map((c, i) => (
              <Chip key={c} on={f.cats.includes(i)} onClick={() => toggleCat(i)}>{c}</Chip>
            ))}
            <Chip on={f.other} onClick={() => set({ ...f, other: !f.other })}>显示「其他」</Chip>
          </div>
          <div className="bf-frow">
            <span className="bf-flabel">年份</span>
            <Chip on={f.year === ALL_YEARS} onClick={() => set({ ...f, year: ALL_YEARS })}>全部</Chip>
            {years.map((y) => (
              <Chip key={y} on={f.year === y} onClick={() => set({ ...f, year: y })}>{y}</Chip>
            ))}
          </div>
          <div className="bf-frow">
            <span className="bf-flabel">来源</span>
            <Chip on={f.file === ALL_FILES} onClick={() => set({ ...f, file: ALL_FILES })}>全部</Chip>
            {files.map((name, i) => (
              <Chip key={name} on={f.file === i} onClick={() => set({ ...f, file: i })}>{name}</Chip>
            ))}
          </div>
          <div className="bf-frow">
            <span className="bf-flabel">最低票数</span>
            {VOTE_OPTIONS.map((v) => (
              <Chip key={v} on={f.minVotes === v} onClick={() => set({ ...f, minVotes: v })}>{v === 0 ? '不限' : `≥ ${v}`}</Chip>
            ))}
            <button type="button" onClick={() => set(defaultFilter())} className="bf-fchip">重置</button>
          </div>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-zinc-400">
          当前口径：{scope}。票数门槛只作用于 OzBargain 的行，其他来源没有票数，不受影响。页面顶部的数字和「好价什么时候出」用的是未筛选的全量数据。
        </p>
        <LazyDetails
          className="mt-3 text-sm"
          summary={`已排除 ${excludedShown.length} 条异常（合约/会员等带条件、折扣超过 90%、价格低于 $5）`}
        >
          {() => (
            <div className="mt-3 overflow-x-auto rounded-lg border border-zinc-800">
              <table className={TABLE_CLASS} style={{ minWidth: 560 }}>
                <thead><tr><th>商品</th><th>年份</th><th>到手价</th><th>原价</th><th>折扣</th><th>排除原因</th></tr></thead>
                <tbody>
                  {excludedShown.map((r, i) => (
                    <tr key={i}>
                      <td><Link href={unpackUrl(r[7])}>{r[6]}</Link></td>
                      <td className="tabular-nums">{r[1]}</td>
                      <td className="tabular-nums">{money(r[3])}</td>
                      <td className="tabular-nums">{money(r[4])}</td>
                      <td className="tabular-nums">{r[2]}%</td>
                      <td>{r[5]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </LazyDetails>
      </Section>

      {recShown.length > 0 && (
        <Section id="recurring" emoji="🔥" title="今年大概率会打折（往年两年黑五都出现过）">
          {CATEGORIES.map((category, cat) => {
            const mine = recShown.filter((r) => r[0] === cat).sort((a, b) => b[5] - a[5] || b[3] - a[3])
            if (mine.length === 0) return null
            return (
              <div key={category} className="mb-6">
                <SubHead>{category}</SubHead>
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {mine.map((r) => (
                    <li key={r[7]} className="bf-rcard">
                      <Thumb image={r[8] || undefined} name={r[1]} category={category} size={88} />
                      <div className="bf-rname">{r[1]}</div>
                      <div className="bf-rprice">预计 {money(r[3])}<span className="bf-mf"> 左右</span></div>
                      <div className="bf-mn">2024 {money(r[2])} → 2025 {money(r[3])}</div>
                      <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
                        <span className={TREND_CHIP[r[4]]}>{TREND_ARROW[r[4]]} {r[4]}</span>
                        <Link href={unpackUrl(r[6])}><span className="bf-m">来源</span></Link>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
          {brands.length > 0 && (
            <div>
              <SubHead>每年都有折扣的品牌：</SubHead>
              <ul className="flex flex-wrap gap-2">
                {brands.map((b) => <li key={b.name} className="bf-brand">{b.name}</li>)}
              </ul>
            </div>
          )}
          <Evidence>依据：OzBargain 和人工核对的 2024、2025 年黑五季无附加条件的价格，每款取各年最低价，按网友票数排序。这一块和下面的品牌列表固定比 2024 与 2025 两年，年份和来源筛选不适用。</Evidence>
        </Section>
      )}

      <Section id="board" emoji="🏆" title="往年好价榜">
        {blocks.length === 0 ? (
          <p className="text-sm text-zinc-400">当前筛选下没有带原价的好价。放宽票数门槛或多选几个品类试试。</p>
        ) : (
          blocks.map((b) => (
            <div key={b.category} className="mb-6 last:mb-0">
              <SubHead>{b.category} · {b.n} 条{b.n > BOARD_LIMIT ? `，列出票数/折扣最高的 ${BOARD_LIMIT} 条` : ''}</SubHead>
              <div className="overflow-x-auto rounded-lg border border-zinc-800">
                <table className={TABLE_CLASS} style={{ minWidth: 640 }}>
                  <thead>
                    <tr><th>商品</th><th>年份</th><th>商家</th><th>到手价</th><th>原价</th><th>折扣</th><th>票数</th></tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, i) => (
                      <tr key={i}>
                        <td><Link href={unpackUrl(r[10])}>{r[8]}</Link></td>
                        <td className="tabular-nums">{r[2]}{r[1] === BD_EVENT ? ' 节礼日' : ''}</td>
                        <td>{r[9]}</td>
                        <td className="font-bold tabular-nums text-zinc-50">{money(r[6])}</td>
                        <td className="tabular-nums">{money(r[7])}</td>
                        <td className="tabular-nums">{r[5]}%</td>
                        <td className="tabular-nums">{r[4] === NO_VOTES ? '—' : r[4]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
        <Evidence>依据：有原价、已排除异常的黑五季和节礼日好价，每个品类最多 {BOARD_LIMIT} 条。有票数的按票数排，没有票数的按折扣排。票数只有 OzBargain 有。</Evidence>
      </Section>

      {depth.length > 0 && (
        <Section emoji="🏷️" title="今年各品类预计打几折">
          <Takeaway>
            {ranked.length >= 3
              ? `${ranked[0].category}、${ranked[1].category}折扣最深，${ranked[ranked.length - 1].category}最浅`
              : ranked.length > 0
                ? `${ranked[0].category}折扣最深`
                : '当前筛选下样本都不足，放宽票数门槛再看'}
          </Takeaway>
          <Bars
            rows={depth.map((c) => ({
              label: c.median == null ? `${c.category} · 样本不足（${c.n} 条，少于 ${MIN_SAMPLE} 条不出中位数）` : `${c.category} · 约便宜 ${c.median}%（${c.n} 条）`,
              value: c.median ?? 0,
              text: c.median == null ? '—' : `${c.median}%`,
              accent: ranked.length > 0 && c.cat === ranked[0].cat,
              title: c.median == null ? `${c.category}：${c.n} 条，样本不足` : `${c.category}：中位便宜 ${c.median}%，${c.n} 条`,
            }))}
          />
          <Evidence>依据：{yearText}黑五季有原价的好价折扣中位数；已排除带条件、折扣超过 90%、低于 $5 的；样本少于 {MIN_SAMPLE} 条的品类只写「样本不足」。品类顺序固定，不随筛选重排。</Evidence>
        </Section>
      )}

      <Section id="cheapest" emoji="📉" title="黑五是不是最便宜">
        {sy.pairs === 0 ? (
          <p className="text-sm text-zinc-400">当前筛选下没有同一购物年里既有黑五价、又有别的促销价的商品。</p>
        ) : (
          <>
            <Takeaway>
              同一个购物年里能两边比的 {sy.pairs} 件：黑五更便宜 {sy.bfCheaper} 件，差不多 {sy.same} 件，别的促销更便宜 {sy.otherCheaper} 件
            </Takeaway>
            <Bars
              rows={[
                { label: '黑五更便宜', value: sy.bfCheaper, text: `${sy.bfCheaper} 件`, accent: true, title: `黑五更便宜：${sy.bfCheaper} 件` },
                { label: '差不多（2% 以内）', value: sy.same, text: `${sy.same} 件`, title: `差不多：${sy.same} 件` },
                { label: '别的促销更便宜', value: sy.otherCheaper, text: `${sy.otherCheaper} 件`, title: `别的促销更便宜：${sy.otherCheaper} 件` },
              ]}
            />
            <LazyDetails className="mt-5 text-sm" summary="看明细：每件的黑五价和同一购物年里最低的非黑五价">
              {() => (
              <div className="mt-3 overflow-x-auto rounded-lg border border-zinc-800">
                <table className={TABLE_CLASS} style={{ minWidth: 620 }}>
                  <thead><tr><th>商品</th><th>购物年</th><th>黑五价</th><th>同年最低非黑五价</th><th>在哪个促销</th></tr></thead>
                  <tbody>
                    {sy.rows.map((r, i) => (
                      <tr key={i}>
                        <td><Link href={unpackUrl(r[8])}>{r[7]}</Link></td>
                        <td className="tabular-nums">{r[1]}/{String((r[1] + 1) % 100).padStart(2, '0')}</td>
                        <td className="tabular-nums">{money(r[4])}</td>
                        <td className="tabular-nums">{money(r[5])}</td>
                        <td>{r[6]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              )}
            </LazyDetails>
          </>
        )}
        <Evidence>
          依据：购物年 Y = {'Y'}-06-01 到 {'Y+1'}-05-31，涵盖当年 EOFY、Prime Day、Click Frenzy、黑五和节礼日。每个商品在同一个购物年里取最低的无条件黑五价，和同一年里最低的无条件非黑五价比，差距在 2% 以内算差不多。只比同一购物年，不会拿 2025 年的黑五价去和 2018 年的价格比。
        </Evidence>
      </Section>

      {counts.ratio != null && (
        <Section emoji="⚖️" title="黑五还是节礼日">
          <p className="mb-5 rounded-xl border border-sky-400/20 bg-sky-500/10 p-4 text-base font-bold leading-snug text-zinc-50">
            想买明确的型号 → 黑五（好价是节礼日的 {counts.ratio.toFixed(1)} 倍）；衣服、清仓、Sonos → 节礼日
            {bfMed.median != null && bdMed.median != null && (bdMed.median > bfMed.median ? '（折扣深一点）' : '（折扣差不多）')}
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="bf-card p-4">
              <SubHead>每年好价数量</SubHead>
              <Bars
                rows={[
                  { label: '黑五', value: counts.bfPerYear, text: String(Math.round(counts.bfPerYear)), accent: true, title: `黑五：每年约 ${Math.round(counts.bfPerYear)} 条` },
                  { label: '节礼日', value: counts.bdPerYear, text: String(Math.round(counts.bdPerYear)), title: `节礼日：每年约 ${Math.round(counts.bdPerYear)} 条` },
                ]}
              />
            </div>
            <div className="bf-card p-4">
              <SubHead>中位折扣</SubHead>
              <Bars
                rows={[
                  { label: `黑五（${bfMed.n} 条）`, value: bfMed.median ?? 0, text: bfMed.median == null ? '样本不足' : `${bfMed.median}%`, title: `黑五：${bfMed.n} 条` },
                  { label: `节礼日（${bdMed.n} 条）`, value: bdMed.median ?? 0, text: bdMed.median == null ? '样本不足' : `${bdMed.median}%`, accent: bdMed.median != null && bfMed.median != null && bdMed.median > bfMed.median, title: `节礼日：${bdMed.n} 条` },
                ]}
              />
            </div>
          </div>
          <Evidence>依据：黑五季 Y 只和节礼日季 Y 比（节礼日 1 月的价算上一季），数量是 {counts.years.join('、')} 年的每年平均；数量只算 OzBargain，折扣用全部来源，口径同上。样本少于 {MIN_SAMPLE} 条写「样本不足」。</Evidence>
        </Section>
      )}
    </>
  )
}
