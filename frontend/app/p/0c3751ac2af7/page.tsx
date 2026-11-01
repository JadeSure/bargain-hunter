import type { Metadata } from 'next'
import {
  addDays,
  categoryDepth,
  bfVsBoxing,
  daysBetween,
  earlyVsBfDay,
  fileCoverage,
  giftDepth,
  forecast,
  keyHistory,
  loadBf2026,
  money,
  monthDay,
  recurring,
  recurringBrands,
  timingDepth,
  timingShares,
  weekday,
  weekPlan,
} from '@/lib/bf2026'
import type { PrepStep, Recurring } from '@/lib/bf2026'
import Bars from '@/app/components/bf2026/Bars'
import Cards from '@/app/components/bf2026/Cards'
import type { WatchCard } from '@/app/components/bf2026/Cards'
import type { HistoryRow } from '@/app/components/bf2026/Lazy'
import Thumb from '@/app/components/bf2026/Thumb'
import { ADVICE, TABLE_CLASS, clip, packUrl, pillFor, verifyLabel } from '@/app/components/bf2026/shared'

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
const GIFT_BLOCKS: [match: string, title: string, emoji: string][] = [
  ['国内亲友', '送国内亲友', '👵'],
  ['伴侣', '送伴侣/家人', '❤️'],
  ['Secret Santa', '同事 Secret Santa', '🎄'],
]
const BUY_ICON: Record<string, string> = {
  'giftcard-stack': '💳',
  'officeworks-match': '🏷️',
  'apple-cashback': '💸',
  'mall-voucher': '🛍️',
  danmurphys: '🍷',
}
const PICK_EMOJI: [keyword: string, emoji: string][] = [
  ['iPhone', '📱'],
  ['包', '👜'],
  ['IKEA', '🛋️'],
  ['ALO', '🧘'],
  ['DJI', '📷'],
  ['BioCeuticals', '💊'],
  ['空气炸锅', '🍟'],
  ['Breville', '☕'],
  ['雅诗兰黛', '💄'],
  ['Roborock', '🤖'],
]
// Short recipient labels: only the 送-type parts of `who` (自用 is dropped), e.g. 送伴侣家人 -> 伴侣家人.
const giftWho = (who: string) => who.split(' / ').filter((w) => w.startsWith('送') || w.includes('Santa')).map((w) => w.replace(/^送/, ''))
const pickEmoji = (title: string) => PICK_EMOJI.find(([k]) => title.includes(k))?.[1] ?? '🔥'
const TREND_CHIP: Record<string, string> = {
  降价中: 'bf-emerald',
  涨价了: 'bf-rose',
  差不多: 'bf-zinc',
}
const TREND_ARROW: Record<string, string> = { 降价中: '↓', 涨价了: '↑', 差不多: '→' }

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
      className="bf-link"
    >
      {children}
    </a>
  )
}

function Section({ id, emoji, title, children }: { id?: string; emoji: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="bf-section">
      <h2 className="mb-5 text-xl font-semibold text-zinc-50">
        <span aria-hidden className="mr-2">{emoji}</span>{title}
      </h2>
      {children}
    </section>
  )
}

const Takeaway = ({ children }: { children: React.ReactNode }) => <p className="mb-5 text-lg font-bold leading-snug text-zinc-50 sm:text-xl">{children}</p>
const Evidence = ({ children }: { children: React.ReactNode }) => <p className="mt-5 text-xs leading-relaxed text-zinc-400">{children}</p>
const SubHead = ({ children }: { children: React.ReactNode }) => <h3 className="mb-3 text-sm font-semibold text-zinc-300">{children}</h3>

function Step({ s, today }: { s: PrepStep; today: string }) {
  return (
    <li className="bf-step">
      <span aria-hidden className="bf-check" />
      <div className="bf-step-body">
        <div className="min-w-0 flex-1 basis-48">
          <div className="font-bold text-zinc-50"><Src href={s.source}>{s.task}</Src></div>
          <div className="bf-detail">{s.detail}</div>
        </div>
        <span className="bf-due">截止 {monthDay(s.by)} · {inDays(daysBetween(today, s.by))}</span>
      </div>
    </li>
  )
}

function RecurringCard({ r, image }: { r: Recurring; image?: string }) {
  return (
    <li className="bf-rcard">
      <Thumb image={image} name={r.item} category={r.category} size={88} />
      <div className="bf-rname">{clip(r.item, 50)}</div>
      <div className="bf-rprice">预计 {money(r.p2025)}<span className="bf-mf"> 左右</span></div>
      <div className="bf-mn">2024 {money(r.p2024)} → 2025 {money(r.p2025)}</div>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
        <span className={`${TREND_CHIP[r.trend]}`}>{TREND_ARROW[r.trend]} {r.trend}</span>
        <Src href={r.source}><span className="bf-m">来源</span></Src>
      </div>
    </li>
  )
}

const Th = ({ children }: { children: React.ReactNode }) => <th>{children}</th>
const Td = ({ children }: { children: React.ReactNode }) => <td>{children}</td>

type TimelineKind = 'today' | 'deadline' | 'sale' | 'major'
const DOT: Record<TimelineKind, string> = {
  today: 'h-5 w-5 bg-zinc-50 ring-4 ring-zinc-50/20',
  deadline: 'h-3 w-3 bg-orange-400',
  sale: 'h-3 w-3 bg-sky-400',
  major: 'h-6 w-6 bg-sky-400 ring-4 ring-sky-400/25 text-xs',
}

export default async function Bf2026Page() {
  const { points, watch, calendar, prep, rules, facts, signals, images, gifts, errors } = await loadBf2026()
  const today = sydneyToday()
  const daysLeft = daysBetween(today, BF_DATE)
  const fc = forecast(watch, points)
  const files = fileCoverage(points)
  const tm = timingShares(points)
  const td = timingDepth(points)
  const ev = earlyVsBfDay(points)
  const gd = giftDepth(points, watch, gifts)
  const rec = recurring(points, watch)
  const brands = recurringBrands(points)
  const depth = categoryDepth(points)
  const vs = bfVsBoxing(points)
  const plan = weekPlan(prep, today)
  const d10 = addDays(BF_DATE, -10)
  const d11 = addDays(BF_DATE, -11)
  const cal = (id: string) => calendar.find((e) => e.id === id)

  // ── timeline ──
  const timeline: { date: string; label: string; kind: TimelineKind }[] = [
    { date: today, label: '今天', kind: 'today' as const },
    ...[...new Set(prep.map((p) => p.by))].map((by) => {
      const steps = prep.filter((p) => p.by === by)
      return { date: by, label: `截止：${steps.slice(0, 3).map((p) => p.task).join('；')}${steps.length > 3 ? ` 等 ${steps.length} 件` : ''}`, kind: 'deadline' as const }
    }),
    ...['s11', 'd10', 'amazon', 'jb', 'bf', 'cm', 'bd-open', 'boxing'].flatMap((id) => {
      const e = cal(id)
      return e ? [{ date: e.start, label: e.event, kind: id === 'bf' || id === 'boxing' ? ('major' as const) : ('sale' as const) }] : []
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
  const depthSub = (b: { n: number; median: number | null }) => (b.median == null ? undefined : b.n < 10 ? '样本少' : `中位便宜 ${b.median}%`)
  const depthLine =
    td.before.median != null && td.after.median != null
      ? td.after.median > td.before.median
        ? `力度：黑五当天和之后折扣略深（约 ${td.after.median}% vs 之前约 ${td.before.median}%，仅供参考）`
        : `力度：前后差不多（约 ${td.after.median}% vs ${td.before.median}%，仅供参考）`
      : null
  const giftMax = Math.max(...gd.bands.flatMap((b) => b.items.map((i) => i.pct)), 1)
  const beforeTens = NUMERALS[Math.round(tm.beforeShare * 10)]

  // ── forecast cards ──
  const shortAdvice = (v: string) => ADVICE.find((a) => a.verdict === v)?.short ?? v
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
      category: f.watch.category,
      image: images[f.watch.key]?.image,
      advice: shortAdvice(f.watch.verdict),
      verdict: f.watch.verdict,
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
  const groups = ADVICE.map(({ verdict, title }) => ({ verdict, title, cards: fc.filter((f) => f.watch.verdict === verdict).map(buildCard) })).filter((g) => g.cards.length > 0)
  const known = ADVICE.map((a) => a.verdict)
  const otherCards = fc.filter((f) => !known.includes(f.watch.verdict))
  if (otherCards.length) groups.push({ verdict: '', title: '其他', cards: otherCards.map(buildCard) })

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
  const latestRetrieved = points.map((p) => p.retrieved_at).reduce((a, b) => (a > b ? a : b), '')

  const navItems = [
    ['todo', '这周要做'],
    ['dates', '关键日期'],
    ['forecast', '预测'],
    ...(recByCat.length > 0 ? [['recurring', '大概率打折']] : []),
    ['gifts', '送礼'],
    ...(signals.length > 0 ? [['buy', '怎么买']] : []),
  ]

  return (
    <main lang="zh-CN" className="mx-auto w-full max-w-4xl space-y-8 px-4 py-6 text-[15px] leading-relaxed text-zinc-200 sm:px-6 sm:py-10">
      <header className="rounded-3xl border border-zinc-800/60 bg-gradient-to-br from-orange-500/20 via-rose-500/10 to-transparent p-5 sm:p-8">
        <h1 className="text-3xl font-bold leading-tight text-zinc-50 sm:text-4xl">澳洲黑五 2026：预测和准备</h1>
        <div className="mt-6 flex flex-wrap items-end gap-x-4 gap-y-2">
          {daysLeft > 0 && <span className="text-7xl font-extrabold leading-none tabular-nums text-orange-300 sm:text-8xl">{daysLeft}</span>}
          <p className="pb-1 text-lg font-semibold text-zinc-50">
            {daysLeft > 0 ? '天后黑五' : `黑五${inDays(daysLeft)}`} <span className="font-normal text-zinc-300">· {cnDate(BF_DATE)} 周{weekday(BF_DATE)}</span>
          </p>
        </div>
        <p className={`bf-pill mt-4 bg-zinc-950/40 py-1 text-sm tabular-nums text-zinc-200`}>
          <span aria-hidden className="mr-1.5">🎄</span>节礼日 {monthDay(BOXING_DATE)} · {inDays(daysBetween(today, BOXING_DATE))}
        </p>
        {tm.total > 0 && (
          <div className="mt-6 flex gap-3 rounded-2xl border border-sky-400/20 bg-sky-950/60 p-4 text-base font-medium leading-relaxed text-sky-50 sm:text-lg">
            <span aria-hidden>💡</span>
            <p>往年{beforeTens}成好价在黑五当天之前出现，{monthDay(d10)} 最集中。到提醒价就买，没到就等黑五当天。{monthDay(d11)} 前把清单、提醒和礼品卡准备好。</p>
          </div>
        )}
      </header>

      {errors.length > 0 && (
        <div role="alert" className="rounded-2xl border border-amber-500 bg-amber-950 p-4 text-sm text-amber-100">
          <div className="font-semibold">有数据文件读取失败，已跳过：</div>
          <ul className="mt-1 list-disc pl-5">
            {errors.map((e) => <li key={e} className="break-words">{e}</li>)}
          </ul>
        </div>
      )}

      <nav aria-label="快速导航" className="-mx-4 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0">
        <ul className="flex w-max gap-2">
          {navItems.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`} className="bf-chip">
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <Section id="todo" emoji="✅" title="这周要做">
        {plan.now.length === 0 ? (
          <p className="text-sm text-zinc-400">没有待办了。</p>
        ) : (
          <ul className="space-y-3">{plan.now.map((s) => <Step key={s.step} s={s} today={today} />)}</ul>
        )}
        {plan.later.length > 0 && (
          <details className="mt-5">
            <summary className="inline-flex min-h-10 cursor-pointer items-center rounded-full border border-zinc-700/70 px-4 text-sm text-zinc-300 hover:text-zinc-50">
              展开：之后还要做的 {plan.later.length} 步
            </summary>
            {[...new Set(plan.later.map((s) => s.phase))].map((ph) => (
              <div key={ph} className="mt-5">
                <div className="mb-3 text-sm font-semibold text-zinc-100">{ph}</div>
                <ul className="space-y-3">{plan.later.filter((s) => s.phase === ph).map((s) => <Step key={s.step} s={s} today={today} />)}</ul>
              </div>
            ))}
          </details>
        )}
      </Section>

      <Section id="dates" emoji="🗓️" title="接下来的关键日期">
        <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-zinc-700">
          {timeline.map((r, i) => (
            <li key={`${r.date}-${i}`} className="relative pl-9">
              <span aria-hidden className={`bf-dot ${DOT[r.kind]}`}>
                {r.kind === 'major' && (r.label.includes('节礼') ? '🎄' : '🛍️')}
              </span>
              <div className="bf-tl-row">
                <span className={`bf-tl-date ${r.kind === 'today' ? 'text-zinc-50' : 'text-zinc-100'}`}>
                  {monthDay(r.date)} 周{weekday(r.date)}
                </span>
                <span className={`bf-tl-label ${r.kind === 'major' ? 'font-semibold text-zinc-50' : r.kind === 'today' ? 'font-semibold text-zinc-50' : 'text-zinc-300'}`}>
                  {r.label}
                </span>
                <span className="bf-tl-days">
                  {r.date === today ? '' : inDays(daysBetween(today, r.date))}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      {tm.total > 0 && (
        <Section emoji="⏰" title="好价什么时候出">
          <Takeaway>
            <span className="block">数量：{beforePct}% 在黑五当天之前就出了</span>
            {depthLine && <span className="mt-1 block">{depthLine}</span>}
          </Takeaway>
          <Bars rows={timingLabels.map((label, i) => ({ label, value: tm.pct[i], text: `${tm.pct[i]}%`, sub: depthSub(td.buckets[i]), accent: i < 3 }))} />
          {(ev.deepBefore > 0 || ev.pairs > 0) && (
            <div className="bf-card mt-5 space-y-3 p-4">
              {ev.deepBefore > 0 && (
                <div className="flex gap-3">
                  <span aria-hidden>🏃</span>
                  <div className="min-w-0">
                    <p className="font-semibold text-zinc-50">黑五前也常有超低价 → 到提醒价就买</p>
                    <p className="bf-m">往年黑五前便宜一半以上的好价 {ev.deepBefore} 个，黑五当天及之后 {ev.deepAfter} 个</p>
                  </div>
                </div>
              )}
              {ev.pairs > 0 && (
                <div className="flex gap-3">
                  <span aria-hidden>⏳</span>
                  <div className="min-w-0">
                    <p className="font-semibold text-zinc-50">{ev.beforeCheaper > ev.afterCheaper ? '同一件东西，黑五前反而常更便宜 → 到提醒价就买' : '同一件东西，黑五当天及之后一般更便宜或持平 → 没到提醒价就等黑五'}</p>
                    <p className="bf-m">黑五前和黑五当天及之后都有价的同款 {ev.pairs} 件：黑五当天及之后更便宜 {ev.afterCheaper} 件，差不多 {ev.same} 件，黑五前更便宜 {ev.beforeCheaper} 件（样本小，且降价了才常有人再发帖，仅供参考）</p>
                  </div>
                </div>
              )}
            </div>
          )}
          <Evidence>依据：OzBargain 2024、2025 年黑五季 {tm.total} 条好价的发帖日期；折扣只算有原价的 {td.total} 条，各类商品混在一起，仅供参考</Evidence>
        </Section>
      )}

      <Section id="forecast" emoji="🔮" title="今年预测：你关注的东西">
        <Cards groups={groups} />
      </Section>

      {recByCat.length > 0 && (
        <Section id="recurring" emoji="🔥" title="今年大概率会打折（往年两年黑五都出现过）">
          {recByCat.map((c) => (
            <div key={c.category} className="mb-6">
              <SubHead>{c.category}</SubHead>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">{c.rows.map((r) => <RecurringCard key={r.key} r={r} image={images[r.key]?.image} />)}</ul>
            </div>
          ))}
          {brands.length > 0 && (
            <div>
              <SubHead>每年都有折扣的品牌：</SubHead>
              <ul className="flex flex-wrap gap-2">
                {brands.map((b) => <li key={b.name} className="bf-brand">{b.name}</li>)}
              </ul>
            </div>
          )}
          <Evidence>依据：OzBargain 和人工核对的 2024、2025 年黑五季无附加条件的价格，每款取各年最低价，按网友票数排序</Evidence>
        </Section>
      )}

      {depthRows.length > 0 && (
        <Section emoji="🏷️" title="今年各品类预计打几折">
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
        <Section emoji="⚖️" title="黑五还是节礼日">
          <p className="mb-5 rounded-xl border border-sky-400/20 bg-sky-500/10 p-4 text-base font-bold leading-snug text-zinc-50">
            想买明确的型号 → 黑五（好价是节礼日的 {vs.ratio.toFixed(1)} 倍）；衣服、清仓、Sonos → 节礼日
            {vs.bfMedian != null && vs.bdMedian != null && (vs.bdMedian > vs.bfMedian ? '（折扣深一点）' : '（折扣差不多）')}
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="bf-card p-4">
              <SubHead>每年好价数量</SubHead>
              <Bars
                rows={[
                  { label: '黑五', value: vs.bfPerYear, text: String(Math.round(vs.bfPerYear)), accent: true },
                  { label: '节礼日', value: vs.bdPerYear, text: String(Math.round(vs.bdPerYear)) },
                ]}
              />
            </div>
            {vs.bfMedian != null && vs.bdMedian != null && (
              <div className="bf-card p-4">
                <SubHead>中位折扣</SubHead>
                <Bars
                  rows={[
                    { label: '黑五', value: vs.bfMedian, text: `${vs.bfMedian}%` },
                    { label: '节礼日', value: vs.bdMedian, text: `${vs.bdMedian}%`, accent: vs.bdMedian > vs.bfMedian },
                  ]}
                />
              </div>
            )}
          </div>
          <Evidence>依据：2024、2025 年两个季节的平均；数量只算 OzBargain，折扣用全部来源</Evidence>
        </Section>
      )}

      <Section id="gifts" emoji="🎁" title="送礼">
        <h3 className="mb-4 text-lg font-bold text-zinc-50">折扣力度对比：哪些礼物最划算</h3>
        <p className="bf-m -mt-2 mb-4">便宜多少按商家标的原价算；不少东西平时就打折，到底划不划算看上面卡片里的提醒价。</p>
        <div className="mb-8 space-y-6">
          {gd.bands.filter((b) => b.items.length > 0).map((b) => (
            <div key={b.title}>
              <SubHead>{b.title}</SubHead>
              <ul className="space-y-3">
                {b.items.map((i) => (
                  <li key={i.key} className="flex items-start gap-3">
                    <Thumb image={images[i.key]?.image} name={i.name} category={i.category} size={40} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="bf-gname">{i.name}</span>
                        {giftWho(i.who).map((w) => <span key={w} className="bf-zinc">{w}</span>)}
                      </div>
                      <div className="bf-barrow">
                        <div className="bf-track">
                          <div className="bf-fill from-sky-400 to-indigo-500" style={{ width: `${(i.pct / giftMax) * 100}%` }} />
                        </div>
                        <span className="shrink-0 font-bold tabular-nums text-zinc-50">便宜 {i.pct}%</span>
                      </div>
                      <div className="bf-m mt-1 tabular-nums">
                        {money(i.was)} → {money(i.price)}（{i.year} 黑五）{' '}<Src href={i.source}>来源</Src>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {gd.noData.length > 0 && <p className="bf-m">没有原价数据：{gd.noData.join('、')}</p>}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {GIFT_BLOCKS.map(([match, title, emoji]) => {
            const rows = fc.filter((f) => f.watch.who.includes(match))
            if (rows.length === 0) return null
            return (
              <div key={title} className="bf-card p-4">
                <h3 className="mb-3 font-semibold text-zinc-50"><span aria-hidden className="mr-1.5">{emoji}</span>{title}</h3>
                <ul className="space-y-3">
                  {rows.map((f) => (
                    <li key={f.watch.key} className="flex items-start gap-2.5">
                      <Thumb image={images[f.watch.key]?.image} name={f.watch.item} category={f.watch.category} size={28} />
                      <div className="bf-grow">
                        <div className="bf-gname">{f.watch.item}</div>
                        <div className="bf-badges">
                          <span className={`${pillFor(f.watch.verdict)}`}>{shortAdvice(f.watch.verdict)}</span>
                          <span className="bf-need">{f.target == null ? '没有可靠价格，看卡片说明' : `到 ${money(f.target)} 就买`}</span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </Section>

      {signals.length > 0 && (
        <Section id="buy" emoji="💡" title="怎么买最便宜">
          {buy.length > 0 && (
            <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
              {buy.map((s) => (
                <div key={s.id} className="bf-card flex flex-col p-4 sm:p-5">
                  <div aria-hidden className="text-3xl">{BUY_ICON[s.id] ?? '💡'}</div>
                  <div className="mt-2 font-bold text-zinc-50">{s.title}</div>
                  <div className="mt-1 break-words text-sm leading-relaxed text-zinc-300">{s.detail}</div>
                  <div className="mt-2 break-words border-l-2 border-zinc-700 pl-3 text-xs italic leading-relaxed text-zinc-400">{s.evidence}</div>
                  {s.link && (
                    <div className="mt-auto pt-4">
                      <a
                        href={s.link}
                        {...(s.link.startsWith('http') ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                        className="inline-flex min-h-9 items-center rounded-full bg-zinc-800 px-4 text-sm font-medium text-zinc-100 hover:bg-zinc-700"
                      >
                        看攻略 →
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {picks.length > 0 && (
            <>
              <SubHead>华人热门（小红书，价格未核实）</SubHead>
              <ul className="grid gap-3 sm:grid-cols-2">
                {picks.map((s) => (
                  <li key={s.id} className="flex min-w-0 gap-3 rounded-xl border border-zinc-800/60 bg-zinc-900 p-3">
                    <span aria-hidden className="text-2xl">{pickEmoji(s.title)}</span>
                    <div className="min-w-0 break-words text-sm">
                      <span className="font-semibold text-zinc-100">{s.title}</span>
                      <span className="text-zinc-400">：{s.detail}</span>
                      {s.link && <> <Src href={s.link}>看攻略 →</Src></>}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}

      <section className="min-w-0 rounded-2xl border border-zinc-800/60 p-5 sm:p-6">
        <details>
          <summary className="cursor-pointer text-base font-semibold text-zinc-400 hover:text-zinc-200">
            <span aria-hidden className="mr-2">📚</span>依据和数据来源
          </summary>
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

          <h3 className="mb-2 mt-6 font-medium text-zinc-100">带回国规则</h3>
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
      </section>
    </main>
  )
}
