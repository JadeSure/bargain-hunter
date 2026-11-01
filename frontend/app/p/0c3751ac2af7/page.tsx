import type { Metadata } from 'next'
import {
  addDays,
  categoryDepth,
  bfVsBoxing,
  daysBetween,
  fileCoverage,
  forecast,
  keyHistory,
  loadBf2026,
  money,
  monthDay,
  recurring,
  recurringBrands,
  timingShares,
  weekday,
  weekPlan,
} from '@/lib/bf2026'
import type { PrepStep, Recurring } from '@/lib/bf2026'
import Bars from '@/app/components/bf2026/Bars'
import Cards from '@/app/components/bf2026/Cards'
import type { WatchCard } from '@/app/components/bf2026/Cards'
import type { HistoryRow } from '@/app/components/bf2026/Lazy'
import { TABLE_CLASS, clip, packUrl, verifyLabel } from '@/app/components/bf2026/shared'

export const metadata: Metadata = {
  title: { absolute: '澳洲黑五 2026：预测和准备' },
  robots: { index: false, follow: false },
}

const BF_DATE = '2026-11-27'
const BOXING_DATE = '2026-12-26'
const HISTORY_ROWS = 6
const TOP_PER_CATEGORY = 6
const CATEGORY_ORDER = ['数码电子', '家电厨房', '美妆个护', '户外运动', '保健食品', '礼品']
const NUMERALS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const ADVICE_GROUPS: [verdict: string, title: string, short: string][] = [
  ['黑五入手', '等黑五买', '等黑五买'],
  ['现在可买', '现在就可以买', '现在可买'],
  ['不用等黑五', '不用等黑五（别的时候更便宜）', '不用等黑五'],
  ['小心虚标', '小心假折扣', '小心假折扣'],
]
const GIFT_BLOCKS: [match: string, title: string][] = [
  ['国内亲友', '送国内亲友'],
  ['伴侣', '送伴侣/家人'],
  ['Secret Santa', '同事 Secret Santa'],
]

const sydneyToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Sydney' })
const cnDate = (iso: string) => `${Number(iso.slice(5, 7))}月${Number(iso.slice(8, 10))}日`
const inDays = (n: number) => (n === 0 ? '今天' : n > 0 ? `还有 ${n} 天` : `已过 ${-n} 天`)

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

const Takeaway = ({ children }: { children: React.ReactNode }) => <p className="mb-4 font-medium text-zinc-50">{children}</p>
const Evidence = ({ children }: { children: React.ReactNode }) => <p className="mt-4 text-xs text-zinc-400">{children}</p>

function Step({ s, today }: { s: PrepStep; today: string }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden className="mt-1 h-4 w-4 shrink-0 rounded border border-zinc-500" />
      <div className="min-w-0">
        <div className="font-medium text-zinc-50"><Src href={s.source}>{s.task}</Src></div>
        <div className="break-words text-sm text-zinc-400">{s.detail}</div>
        <div className="text-sm text-sky-300">截止 {monthDay(s.by)}（{inDays(daysBetween(today, s.by))}）</div>
      </div>
    </li>
  )
}

function RecurringRow({ r }: { r: Recurring }) {
  return (
    <li className="break-words text-sm">
      <span className="font-medium text-zinc-50">{clip(r.item, 50)}</span> · 预计 {money(r.p2025)} 左右
      <span className="text-zinc-400">（2024 {money(r.p2024)} → 2025 {money(r.p2025)}，{r.trend}）</span>{' '}
      <Src href={r.source}>[来源]</Src>
    </li>
  )
}

const Th = ({ children }: { children: React.ReactNode }) => <th>{children}</th>
const Td = ({ children }: { children: React.ReactNode }) => <td>{children}</td>

export default async function Bf2026Page() {
  const { points, watch, calendar, prep, rules, facts, signals, errors } = await loadBf2026()
  const today = sydneyToday()
  const daysLeft = daysBetween(today, BF_DATE)
  const fc = forecast(watch, points)
  const files = fileCoverage(points)
  const tm = timingShares(points)
  const rec = recurring(points, watch)
  const brands = recurringBrands(points)
  const depth = categoryDepth(points)
  const vs = bfVsBoxing(points)
  const plan = weekPlan(prep, today)
  const d10 = addDays(BF_DATE, -10)
  const d11 = addDays(BF_DATE, -11)
  const cal = (id: string) => calendar.find((e) => e.id === id)
  const rule = (id: string) => rules.find((r) => r.id === id)

  // ── timeline ──
  const timeline = [
    { date: today, label: '今天', due: false },
    ...[...new Set(prep.map((p) => p.by))].map((by) => {
      const steps = prep.filter((p) => p.by === by)
      return { date: by, label: `截止：${steps.slice(0, 3).map((p) => p.task).join('；')}${steps.length > 3 ? ` 等 ${steps.length} 件` : ''}`, due: false }
    }),
    ...['s11', 'd10', 'amazon', 'jb', 'bf', 'cm', 'cn-std', 'cn-exp', 'bd-open', 'boxing'].flatMap((id) => {
      const e = cal(id)
      if (!e) return []
      const due = id === 'cn-std' || id === 'cn-exp'
      return [{ date: e.start, label: due ? e.event.replace('：', '').replace('截止', '') : e.event, due }]
    }),
  ]
    .filter((r) => r.date >= today && r.date <= BOXING_DATE)
    .sort((a, b) => a.date.localeCompare(b.date))

  // ── timing chart ──
  const timingLabels = [
    `黑五前 3 周到前 11 天（11 天，${monthDay(addDays(BF_DATE, -21))} – ${monthDay(d11)}）`,
    `前 10 天（1 天，今年 ${monthDay(d10)}）`,
    `黑五前 9 天到前 1 天（9 天，${monthDay(addDays(BF_DATE, -9))} – ${monthDay(addDays(BF_DATE, -1))}）`,
    `黑五当天（${monthDay(BF_DATE)}）`,
    `黑五之后（${monthDay(addDays(BF_DATE, 1))} 起）`,
  ]
  const beforePct = tm.pct[0] + tm.pct[1] + tm.pct[2]
  const beforeTens = NUMERALS[Math.round(tm.beforeShare * 10)]

  // ── forecast cards ──
  const buildCard = (f: (typeof fc)[number]): WatchCard => {
    const hist = keyHistory(points, f.watch.key, HISTORY_ROWS)
    const tp = f.targetPoint
    const now = f.newest26
    const nowFresh = now != null && daysBetween(now.date.length === 10 ? now.date : `${now.date}-01`, today) <= 60
    const [a, b] = f.seasonMins
    const cheaper = a && b ? (a.point.price < b.point.price ? a : b) : (b ?? a)
    return {
      key: f.watch.key,
      item: f.watch.item,
      who: f.watch.who,
      why: f.watch.why,
      confidence: f.confidence,
      range: f.range_text,
      earliest: f.earliest ? monthDay(`2000-${f.earliest}`) : null,
      bar:
        now && nowFresh && f.low != null
          ? [`现在（${now.date.length === 10 ? monthDay(now.date) : `${Number(now.date.slice(5, 7))} 月`}）`, now.price, money(now.price), f.low, money(f.low)]
          : null,
      kw: f.kw,
      broad: !!f.watch.broad,
      basis: tp ? [clip(tp.item), tp.date, tp.file, verifyLabel(tp.file), tp.source] : null,
      seasons: cheaper
        ? { text: f.seasonMins.map((m) => `${m.year} 黑五 ${money(m.point.price)}`).join(' → '), link: cheaper.point.source }
        : null,
      summary: `全部来源 ${hist.n} 个价格点${hist.latest ? ` · 最近 ${money(hist.latest.price)}（${hist.latest.date}${hist.latest.conditions ? `，${hist.latest.conditions}` : ''}）` : ''}`,
      rows: hist.rows.map((r): HistoryRow => [r.date, r.event, r.price, r.conditions, r.retailer, packUrl(r.source)]),
      more: Math.max(0, hist.n - HISTORY_ROWS),
    }
  }
  const groups = ADVICE_GROUPS.map(([verdict, title]) => ({ title, cards: fc.filter((f) => f.watch.verdict === verdict).map(buildCard) })).filter((g) => g.cards.length > 0)
  const known = ADVICE_GROUPS.map((g) => g[0])
  const otherCards = fc.filter((f) => !known.includes(f.watch.verdict))
  if (otherCards.length) groups.push({ title: '其他', cards: otherCards.map(buildCard) })
  const shortAdvice = (v: string) => ADVICE_GROUPS.find((g) => g[0] === v)?.[2] ?? v

  // ── recurring ──
  const recByCat = CATEGORY_ORDER.map((category) => ({
    category,
    rows: rec.filter((r) => r.category === category).sort((a, b) => b.votes - a.votes || b.p2025 - a.p2025).slice(0, TOP_PER_CATEGORY),
  })).filter((c) => c.rows.length > 0)

  // ── category depth ──
  const depthRows = CATEGORY_ORDER.flatMap((c) => depth.filter((x) => x.category === c))
  const ranked = [...depthRows].sort((a, b) => b.median - a.median || a.n - b.n)
  const depthTakeaway =
    ranked.length >= 3
      ? `${ranked[0].category}、${ranked[1].category}折扣最深，${ranked[ranked.length - 1].category}最浅`
      : ranked.length > 0
        ? `${ranked[0].category}折扣最深`
        : ''

  const buy = signals.filter((s) => s.kind === '买法')
  const picks = signals.filter((s) => s.kind === '选品')
  const cnStd = cal('cn-std')
  const parcel = rule('parcel')
  const tax = rule('tax50')
  const latestRetrieved = points.map((p) => p.retrieved_at).reduce((a, b) => (a > b ? a : b), '')

  return (
    <main lang="zh-CN" className="mx-auto w-full max-w-3xl px-4 py-8 text-zinc-200 sm:px-6">
      <header>
        <h1 className="text-3xl font-bold text-zinc-50">澳洲黑五 2026：预测和准备</h1>
        <p className="mt-2 text-sm text-zinc-400">
          黑五 {cnDate(BF_DATE)}（{inDays(daysLeft)}）· 节礼日 {cnDate(BOXING_DATE)}
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

      {tm.total > 0 && (
        <div className="mt-6 rounded-lg border border-sky-700 bg-sky-950 p-4 text-lg font-medium text-sky-50">
          往年{beforeTens}成好价在黑五当天之前出现，{monthDay(d10)} 最集中。{monthDay(d11)} 前把清单、提醒和礼品卡准备好。
        </div>
      )}

      <Section title="这周要做">
        {plan.now.length === 0 ? (
          <p className="text-sm text-zinc-400">没有待办了。</p>
        ) : (
          <ul className="space-y-4">{plan.now.map((s) => <Step key={s.step} s={s} today={today} />)}</ul>
        )}
        {plan.later.length > 0 && (
          <details className="mt-5">
            <summary className="cursor-pointer text-sm text-zinc-300">之后还要做的 {plan.later.length} 步</summary>
            {[...new Set(plan.later.map((s) => s.phase))].map((ph) => (
              <div key={ph} className="mt-4">
                <div className="mb-2 text-sm font-medium text-zinc-100">{ph}</div>
                <ul className="space-y-4">{plan.later.filter((s) => s.phase === ph).map((s) => <Step key={s.step} s={s} today={today} />)}</ul>
              </div>
            ))}
          </details>
        )}
      </Section>

      <Section title="接下来的关键日期">
        <ol className="space-y-2">
          {timeline.map((r, i) => (
            <li key={`${r.date}-${i}`} className="flex items-baseline gap-3 text-sm">
              <span className={`w-24 shrink-0 rounded px-2 py-0.5 text-center tabular-nums ${r.date === today ? 'bg-sky-400 font-semibold text-zinc-900' : 'bg-zinc-800 text-zinc-100'}`}>
                {monthDay(r.date)} 周{weekday(r.date)}
              </span>
              <span className="min-w-0 flex-1 break-words">
                {r.due && <span className="mr-1 font-semibold text-amber-400">截止</span>}
                {r.label}
              </span>
              <span className="shrink-0 text-zinc-400">{r.date === today ? '' : inDays(daysBetween(today, r.date))}</span>
            </li>
          ))}
        </ol>
      </Section>

      {tm.total > 0 && (
        <Section title="好价什么时候出">
          <Takeaway>别等黑五当天：{beforePct}% 在之前就出了</Takeaway>
          <Bars rows={timingLabels.map((label, i) => ({ label, value: tm.pct[i], text: `${tm.pct[i]}%`, accent: i < 3 }))} />
          <Evidence>依据：OzBargain 2024、2025 年黑五季 {tm.total} 条好价的发帖日期</Evidence>
        </Section>
      )}

      <Section title="今年预测：你关注的东西">
        <Cards groups={groups} />
      </Section>

      {recByCat.length > 0 && (
        <Section title="今年大概率会打折（往年两年黑五都出现过）">
          {recByCat.map((c) => (
            <div key={c.category} className="mb-5">
              <h3 className="mb-2 font-medium text-zinc-100">{c.category}</h3>
              <ul className="space-y-2">{c.rows.map((r) => <RecurringRow key={r.key} r={r} />)}</ul>
            </div>
          ))}
          {brands.length > 0 && (
            <p className="mt-4 text-sm">
              <span className="font-medium text-zinc-100">每年都有折扣的品牌：</span>
              {brands.map((b) => b.name).join('、')}
            </p>
          )}
          <Evidence>依据：OzBargain 和人工核对的 2024、2025 年黑五季无附加条件的价格，每款取各年最低价，按网友票数排序</Evidence>
        </Section>
      )}

      {depthRows.length > 0 && (
        <Section title="今年各品类预计打几折">
          <Takeaway>{depthTakeaway}</Takeaway>
          <Bars
            rows={depthRows.map((c) => ({
              label: `${c.category} · 约便宜 ${c.median}%（${c.n} 条）`,
              value: c.median,
              text: `${c.median}%`,
              accent: c === ranked[0],
            }))}
          />
          <Evidence>依据：2024、2025 年黑五季有原价的好价折扣中位数；已排除带条件、折扣超过 90%、低于 $5 的；样本少于 5 条的品类不显示</Evidence>
        </Section>
      )}

      {vs.ratio != null && (
        <Section title="黑五还是节礼日">
          <Takeaway>
            想买明确的型号 → 黑五（好价是节礼日的 {vs.ratio.toFixed(1)} 倍）；衣服、清仓、Sonos → 节礼日
            {vs.bfMedian != null && vs.bdMedian != null && (vs.bdMedian > vs.bfMedian ? '（折扣深一点）' : '（折扣差不多）')}
          </Takeaway>
          <h3 className="mb-2 text-sm font-medium text-zinc-100">每年好价数量</h3>
          <Bars
            rows={[
              { label: '黑五', value: vs.bfPerYear, text: String(Math.round(vs.bfPerYear)), accent: true },
              { label: '节礼日', value: vs.bdPerYear, text: String(Math.round(vs.bdPerYear)) },
            ]}
          />
          {vs.bfMedian != null && vs.bdMedian != null && (
            <>
              <h3 className="mb-2 mt-6 text-sm font-medium text-zinc-100">中位折扣</h3>
              <Bars
                rows={[
                  { label: '黑五', value: vs.bfMedian, text: `${vs.bfMedian}%` },
                  { label: '节礼日', value: vs.bdMedian, text: `${vs.bdMedian}%`, accent: vs.bdMedian > vs.bfMedian },
                ]}
              />
            </>
          )}
          <Evidence>依据：2024、2025 年两个季节的平均；数量只算 OzBargain，折扣用全部来源</Evidence>
        </Section>
      )}

      <Section title="送礼">
        <div className="space-y-5">
          {GIFT_BLOCKS.map(([match, title]) => {
            const rows = fc.filter((f) => f.watch.who.includes(match))
            if (rows.length === 0) return null
            return (
              <div key={title}>
                <h3 className="mb-2 font-medium text-zinc-100">{title}</h3>
                <ul className="space-y-1 text-sm">
                  {rows.map((f) => (
                    <li key={f.watch.key} className="break-words">
                      {f.watch.item} · {shortAdvice(f.watch.verdict)} · <span className="text-sky-300">{f.target == null ? '没有可靠价格，看卡片说明' : `到 ${money(f.target)} 就买`}</span>
                    </li>
                  ))}
                </ul>
                {match === '国内亲友' && cnStd && parcel && tax && (
                  <p className="mt-2 text-sm text-amber-300">
                    寄回国：标准包裹 {monthDay(cnStd.start)} 截止，每个包裹 ≤ {parcel.value}，{tax.value.replace('应缴税额', '税额')}（见下方规则）
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </Section>

      {signals.length > 0 && (
        <Section title="怎么买最便宜">
          {buy.length > 0 && (
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
          )}
          {picks.length > 0 && (
            <>
              <h3 className="mb-2 font-medium text-zinc-100">华人热门（小红书，价格未核实）</h3>
              <ul className="space-y-2 text-sm">
                {picks.map((s) => (
                  <li key={s.id} className="break-words">
                    <span className="font-medium text-zinc-100">{s.title}</span>：{s.detail}
                    {s.link && <> <Src href={s.link}>看攻略 →</Src></>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}

      <Section title="依据和数据来源">
        <details>
          <summary className="cursor-pointer text-sm text-zinc-300">展开：数据文件、方法、规则</summary>
          <p className="mt-4 text-xs text-zinc-400">数据截至 {latestRetrieved} · 共 {points.length} 条价格</p>
          <div className="mt-2 overflow-x-auto rounded-lg border border-zinc-800">
            <table className={TABLE_CLASS} style={{ minWidth: 640 }}>
              <thead><tr><Th>文件</Th><Th>条数</Th><Th>黑五条数</Th><Th>节礼日条数</Th><Th>年份</Th><Th>最新抓取</Th><Th>核对</Th></tr></thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.file}>
                    <Td>{f.file}</Td><Td>{f.rows}</Td><Td>{f.bf_rows}</Td><Td>{f.boxing_rows}</Td><Td>{f.years}</Td><Td>{f.latest}</Td><Td>{verifyLabel(f.file)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mb-2 mt-6 font-medium text-zinc-100">方法</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>预计黑五价和提醒价：只用没有附加条件（合约、二手等）的价格。预计价是往年黑五的最低价到最近一年的最低价；提醒价取往年黑五最低价和今年已见价里更低的那个。关键词涵盖多种商品的，只用人工核对的点。</li>
            <li>信心：没有附加条件的黑五价出现在 2 个年份以上为高，1 个年份为中，没有为低。</li>
            <li>往年两年都出现：同一个商品在 2024 和 2025 年黑五都有无条件价格（不含「其他」类、关键词涵盖多种商品的、2025 年最低价低于 $50 的）。预计价取 2025 年的最低价；比 2024 年低 5% 以上算降价中。</li>
            <li>已知缺口：没有 2021–2023 年的黑五数据；商品分组比较粗；Dealmoon 的数据没有抽查。</li>
          </ul>

          <h3 className="mb-2 mt-6 font-medium text-zinc-100">寄回国规则</h3>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className={TABLE_CLASS} style={{ minWidth: 640 }}>
              <thead><tr><Th>事项</Th><Th>规则</Th><Th>状态</Th><Th>备注</Th></tr></thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id}>
                    <Td><Src href={r.source}>{r.topic}</Src></Td><Td>{r.value}</Td><Td>{r.status}</Td><Td>{r.note}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mb-2 mt-6 font-medium text-zinc-100">其他数据</h3>
          <ul className="space-y-1 text-sm">
            {facts.map((f) => <li key={f.id}><Src href={f.source}>{f.label}</Src>：{f.value}</li>)}
          </ul>
        </details>
      </Section>
    </main>
  )
}
