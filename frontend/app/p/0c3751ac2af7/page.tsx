import type { Metadata } from 'next'
import {
  boxingPairs,
  CATEGORIES,
  comparePairs,
  coverage,
  discounts,
  excludedDiscounts,
  forecast,
  headline,
  keyHistory,
  loadBf2026,
  money,
  timing,
} from '@/lib/bf2026'
import Explorer from '@/app/components/bf2026/Explorer'
import Cards from '@/app/components/bf2026/Cards'
import type { WatchCard } from '@/app/components/bf2026/Cards'
import { PromoYear } from '@/app/components/bf2026/Lazy'
import type { HistoryRow, PromoRow } from '@/app/components/bf2026/Lazy'
import Timing from '@/app/components/bf2026/Timing'
import { TABLE_CLASS, clip, packUrl, verifyLabel } from '@/app/components/bf2026/shared'
import type { DealTuple, ExcludedTuple, PairTuple, SideTuple } from '@/app/components/bf2026/shared'

export const metadata: Metadata = {
  title: { absolute: '澳洲黑五 + 节礼日 2026' },
  robots: { index: false, follow: false },
}

const BF_DATE = '2026-11-27'
const VERDICT_ORDER = ['黑五入手', '现在可买', '不用等黑五', '小心虚标']
const PRD_TARGET = { bfYears: 2, boxingYears: 1, nonBf: 3, retailers: 2 }
const HISTORY_ROWS = 8
const HOT_VOTES = 50

const sydneyToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Sydney' })
const dayNum = (iso: string) => Date.parse(iso + 'T00:00:00Z') / 86400000

function Src({ href, children }: { href: string; children: React.ReactNode }) {
  if (!href.startsWith('http') && !(href.startsWith('/') && !href.startsWith('//'))) return <>{children}</>
  const external = href.startsWith('http')
  return (
    <a
      href={href}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      className="underline underline-offset-2"
    >
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

const Th = ({ children }: { children: React.ReactNode }) => <th>{children}</th>
const Td = ({ children, className }: { children: React.ReactNode; className?: string }) => <td className={className}>{children}</td>
const Scroll = ({ children, min = 640 }: { children: React.ReactNode; min?: number }) => (
  <div className="overflow-x-auto rounded-lg border border-zinc-800">
    <table className={TABLE_CLASS} style={{ minWidth: min }}>{children}</table>
  </div>
)
const Missing = () => <span className="ml-2 font-semibold text-amber-400">缺</span>

// Caliber line under a headline number: which files fed it, and how far they were audited.
const caliber = (files: string[]) =>
  `来源 ${files.length} 个文件${files.includes('dealmoon') ? '，含未抽查的 Dealmoon' : ''}；全部票数；已排除异常`

export default async function Bf2026Page() {
  const { points, promos, watch, calendar, prep, rules, facts, signals, errors } = await loadBf2026()
  const head = headline(points)
  const cmpAll = comparePairs(points)
  const boxAll = boxingPairs(points)
  const fc = forecast(watch, points)
  const cov = coverage(points, watch)
  const today = sydneyToday()
  const daysLeft = Math.round(dayNum(BF_DATE) - dayNum(today))
  const latestRetrieved = points.map((p) => p.retrieved_at).reduce((a, b) => (a > b ? a : b), '')
  const accc = facts.find((f) => f.id === 'accc_2025')
  const verdicts = [...new Set([...VERDICT_ORDER, ...fc.map((f) => f.watch.verdict)])]
  const phases = [...new Set(prep.map((p) => p.phase))]
  const fileNames = cov.files.map((f) => f.file)

  const fileIdx = (f: string) => fileNames.indexOf(f)
  const catIdx = (c: string) => CATEGORIES.indexOf(c as (typeof CATEGORIES)[number])
  const toRow = (event: 0 | 1) => (d: ReturnType<typeof discounts>[number]): DealTuple => [
    clip(d.point.item),
    d.point.retailer,
    packUrl(d.point.source),
    fileIdx(d.point.file),
    catIdx(d.point.category),
    event === 1 && d.point.date.slice(5, 7) === '01' ? Number(d.point.date.slice(0, 4)) - 1 : Number(d.point.date.slice(0, 4)),
    event,
    d.point.price,
    d.point.was_price as number,
    d.pct,
    d.point.id.startsWith('ozb-') && d.point.votes != null ? d.point.votes : -1,
  ]
  const dealRows = [...head.bf.map(toRow(0)), ...head.bd.map(toRow(1))]
  const excluded: ExcludedTuple[] = excludedDiscounts(points).map((e) => [
    clip(e.point.item),
    e.point.price,
    e.point.was_price as number,
    e.pct,
    e.reason,
    packUrl(e.point.source),
  ])
  // Pairs that failed the comparable-item guard keep only what filtering and counting need.
  type Sd = (typeof cmpAll)[number]['bf']
  const sideTuple = (s: Sd, keep: boolean): SideTuple =>
    keep
      ? [clip(s.item), s.price, s.date, s.event, s.retailer, fileIdx(s.file), s.votes ?? -1, packUrl(s.source), s.note]
      : ['', s.price, '', '', '', fileIdx(s.file), s.votes ?? -1, '', '']
  const cmpProps: PairTuple[] = cmpAll.map((c) => [c.key, catIdx(c.category), c.year, c.comparable ? 1 : 0, sideTuple(c.bf, c.comparable), sideTuple(c.other, c.comparable)])
  const boxProps: PairTuple[] = boxAll.map((c) => [c.key, catIdx(c.category), c.year, c.comparable ? 1 : 0, sideTuple(c.bf, c.comparable), sideTuple(c.bd, c.comparable)])
  const years = [...new Set([...dealRows.map((r) => r[5]), ...cmpAll.map((p) => p.year), ...boxAll.map((p) => p.year)])].sort((a, b) => b - a)
  const pairFiles = (sides: { file: string }[]) => [...new Set(sides.map((x) => x.file))]
  const dealFiles = (ds: { point: { file: string } }[]) => [...new Set(ds.map((d) => d.point.file))]
  const cmpOk = cmpAll.filter((p) => p.comparable)

  const winStart = dayNum('2026-11-01')
  const winEnd = dayNum('2027-01-02')
  const winLen = winEnd - winStart + 1
  const pctOf = (iso: string) => Math.min(100, Math.max(0, ((dayNum(iso) - winStart) / winLen) * 100))

  const timingSeries = (event: '黑五季' | '节礼日', lo: number, hi: number) =>
    timing(points, event, lo, hi).map((s) => ({ year: s.year, total: s.total, days: s.days.flatMap((d) => [d.n, d.hot]) }))
  const cards: WatchCard[] = fc.map((f) => {
    const hist = keyHistory(points, f.watch.key, HISTORY_ROWS)
    const tp = f.targetPoint
    const s = f.seen26
    return {
      key: f.watch.key,
      verdict: f.watch.verdict,
      item: f.watch.item,
      who: f.watch.who,
      why: f.watch.why,
      kw: f.kw,
      broad: !!f.watch.broad,
      range: f.range_text,
      seen: s ? [money(s.price), s.date, s.conditions, packUrl(s.source)] : null,
      target: f.target == null ? '—' : money(f.target),
      basis: tp ? [clip(tp.item), tp.date, tp.file, verifyLabel(tp.file), packUrl(tp.source)] : null,
      summary: `全部来源 ${hist.n} 个价格点${hist.latest ? ` · 最近 ${money(hist.latest.price)}（${hist.latest.date}）` : ''}`,
      rows: hist.rows.map((r): HistoryRow => [r.date, r.event, r.price, r.conditions, r.retailer, packUrl(r.source)]),
      more: Math.max(0, hist.n - HISTORY_ROWS),
    }
  })
  const buy = signals.filter((s) => s.kind === '买法')
  const picks = signals.filter((s) => s.kind === '选品')
  const promoYears = [...new Set(promos.map((p) => p.year))].sort((a, b) => b - a)

  return (
    <main lang="zh-CN" className="mx-auto w-full max-w-5xl px-4 py-8 text-zinc-200 sm:px-6">
      <header>
        <h1 className="text-3xl font-bold text-zinc-50">澳洲黑五 + 节礼日 2026</h1>
        <p className="mt-2 text-sm text-zinc-400">
          数据截至 {latestRetrieved} · {points.length} 条价格 · {cov.files.length} 个来源文件 · {promos.length} 条活动
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
        <Tile
          label="往年黑五中位折扣"
          value={head.bf_median != null ? `${head.bf_median}%` : '样本不足'}
          sub={`${head.bf.length} 条 · ${caliber(dealFiles(head.bf))}`}
        />
        <Tile
          label="往年节礼日中位折扣"
          value={head.bd_median != null ? `${head.bd_median}%` : '样本不足'}
          sub={`${head.bd.length} 条 · ${caliber(dealFiles(head.bd))}`}
        />
        <Tile
          label="最低价不在黑五"
          value={`${head.n_beaten} / ${head.n_compare}`}
          sub={`${head.n_compare} 个商品·年（同购物年比较）· ${caliber(pairFiles(cmpOk.flatMap((p) => [p.bf, p.other])))}`}
        />
        <Tile
          label="节礼日比黑五更便宜"
          value={`${head.n_boxing_cheaper} / ${head.n_boxing}`}
          sub={`${head.n_boxing} 个商品·年 · ${caliber(pairFiles(boxAll.filter((p) => p.comparable).flatMap((p) => [p.bf, p.bd])))}`}
        />
        {accc && <Tile label={accc.label} value={accc.value} />}
      </div>

      <Explorer deals={dealRows} excluded={excluded} compare={cmpProps} boxing={boxProps} files={fileNames} years={years} />

      <Section title="哪天开始盯">
        <p className="mb-4 text-sm text-zinc-400">
          每天新出现的带日期好价数量（灰柱）。上方青色空心圆 = 当天有票数 ≥{HOT_VOTES} 的好价。橙色虚线 = 黑五（或 12/26 节礼日）当天。各图同一刻度。
        </p>
        <p className="mb-4 text-sm text-zinc-400">OzBargain 的黑五活动页一般从黑五前 18–19 天才开始有帖，所以最左边几天是空的。</p>
        <Timing title="黑五前后（前 21 天到后 5 天）" lo={-21} hi={5} anchorLabel="黑五" series={timingSeries('黑五季', -21, 5)} />
        <Timing title="节礼日前后（12/20 到 1/15）" lo={-6} hi={20} anchorLabel="12/26" series={timingSeries('节礼日', -6, 20)} />
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
        <Cards verdicts={verdicts} cards={cards} />
      </Section>

      {signals.length > 0 && (
        <Section title="华人怎么买（小红书信号）">
          <p className="mb-4 text-xs text-zinc-400">来自 2026-10-31 人工阅读的小红书笔记，只有标题和点赞数，价格未核实</p>
          {buy.length > 0 && (
            <>
              <h3 className="mb-2 font-medium text-zinc-100">怎么买最便宜</h3>
              <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2">
                {buy.map((s) => (
                  <div key={s.id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                    <div className="font-medium text-zinc-50">{s.title}</div>
                    <div className="mt-1 break-words text-sm">{s.detail}</div>
                    <div className="mt-1 break-words text-xs text-zinc-400">{s.evidence}</div>
                    {s.link && <div className="mt-2 text-sm"><Src href={s.link}>看攻略 →</Src></div>}
                  </div>
                ))}
              </div>
            </>
          )}
          {picks.length > 0 && (
            <>
              <h3 className="mb-2 font-medium text-zinc-100">清单外的热门</h3>
              <ul className="space-y-2 text-sm">
                {picks.map((s) => (
                  <li key={s.id} className="break-words">
                    <span className="font-medium text-zinc-100">{s.title}</span>：{s.detail}
                    <div className="text-xs text-zinc-400">{s.evidence}</div>
                    {s.link && <Src href={s.link}>看攻略 →</Src>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}

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

      <Section title="返现和礼品卡活动">
        {promos.length === 0 ? (
          <p className="text-sm text-zinc-400">还没有活动数据，等数据进来</p>
        ) : (
          promoYears.map((year) => (
            <PromoYear
              key={year}
              year={year}
              rows={promos
                .filter((x) => x.year === year)
                .sort((a, b) => a.retailer.localeCompare(b.retailer))
                .map((x): PromoRow => [x.retailer, x.kind, x.value, x.start ?? '', x.end ?? '', x.scope, x.conditions, packUrl(x.source)])}
            />
          ))
        )}
      </Section>

      <Section title="数据覆盖">
        <Scroll min={760}>
          <thead><tr><Th>文件</Th><Th>条数</Th><Th>黑五条数</Th><Th>节礼日条数</Th><Th>年份</Th><Th>最新抓取</Th><Th>核对</Th></tr></thead>
          <tbody>
            {cov.files.map((f) => (
              <tr key={f.file}>
                <Td>{f.file}</Td><Td>{f.rows}</Td><Td>{f.bf_rows}</Td><Td>{f.boxing_rows}</Td><Td>{f.years}</Td><Td>{f.latest}</Td><Td>{verifyLabel(f.file)}</Td>
              </tr>
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
                <Td>{k.bf_years}{k.bf_years < PRD_TARGET.bfYears && <Missing />}</Td>
                <Td>{k.boxing_years}{k.boxing_years < PRD_TARGET.boxingYears && <Missing />}</Td>
                <Td>{k.non_bf}{k.non_bf < PRD_TARGET.nonBf && <Missing />}</Td>
                <Td>{k.retailers_2026}{k.retailers_2026 < PRD_TARGET.retailers && <Missing />}</Td>
              </tr>
            ))}
          </tbody>
        </Scroll>
      </Section>
    </main>
  )
}
