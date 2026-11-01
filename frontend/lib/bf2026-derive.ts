// Pure data types and derivations for the hidden BF 2026 page. No fs, no relative imports:
// the node selftest imports this file directly.

export const CATEGORIES = ['数码电子', '家电厨房', '美妆个护', '户外运动', '保健食品', '礼品', '其他'] as const

export interface Point {
  id: string
  key: string
  item: string
  model: string | null
  category: string
  retailer: string
  date: string
  event: string
  price: number
  was_price: number | null
  was_suspect: boolean
  conditions: string
  votes: number | null
  history_low: boolean
  source: string
  evidence: string
  retrieved_at: string
  note: string
  file: string
}

export interface Promo {
  id: string
  year: number
  retailer: string
  kind: string
  value: string
  start: string | null
  end: string | null
  scope: string
  conditions: string
  votes: number | null
  source: string
  evidence: string
  retrieved_at: string
  note: string
  file: string
}

export interface Watch {
  key: string
  item: string
  category: string
  who: string
  verdict: string
  why: string
  kw: string
  broad?: boolean
}

export interface CalendarEvent {
  id: string
  event: string
  start: string
  end: string
  date_label: string
  status: string
  note: string
  source: string
}

export interface PrepStep {
  step: number
  phase: string
  by: string
  task: string
  detail: string
  source: string
}

export interface Rule {
  id: string
  topic: string
  value: string
  status: string
  note: string
  source: string
}

export interface Fact {
  id: string
  label: string
  value: string
  source: string
}

export interface Signal {
  id: string
  kind: string
  title: string
  detail: string
  evidence: string
  link: string
}

export interface ItemImage {
  image: string
  page: string
}

export interface Gift {
  key: string
  who: string
}

export interface Bf2026Data {
  points: Point[]
  promos: Promo[]
  watch: Watch[]
  calendar: CalendarEvent[]
  prep: PrepStep[]
  rules: Rule[]
  facts: Fact[]
  signals: Signal[]
  images: Record<string, ItemImage>
  gifts: Gift[]
  errors: string[]
}

// ── Formatting ──────────────────────────────────────────────

export function money(n: number): string {
  const whole = Number.isInteger(n)
  return '$' + n.toLocaleString('en-AU', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 })
}

// ── Basics ──────────────────────────────────────────────────

export const isBf = (p: Point) => p.event === '黑五季'
export const isBoxing = (p: Point) => p.event === '节礼日'
export type SaleEvent = '黑五季' | '节礼日'

export const yearOf = (p: Point) => Number(p.date.slice(0, 4))
// A January Boxing Day sale belongs to the season that started the December before.
export const seasonYear = (p: Point) => (isBoxing(p) && p.date.slice(5, 7) === '01' ? yearOf(p) - 1 : yearOf(p))

// Only OzBargain rows carry meaningful votes; votes on any other source are ignored.
export const isOzb = (p: { id: string }) => p.id.startsWith('ozb-')
export const votesOf = (p: Point): number | null => (isOzb(p) && p.votes != null ? p.votes : null)

const minBy = (ps: Point[]): Point | null => ps.reduce<Point | null>((m, p) => (m && m.price <= p.price ? m : p), null)

export function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2)
}

export const MIN_SAMPLE = 5

// ── Discounts ───────────────────────────────────────────────

export interface Discount {
  point: Point
  pct: number
}

export const MAX_PCT = 90
export const MIN_PRICE = 5

export function discountCandidates(points: Point[], event?: SaleEvent): Discount[] {
  return points
    .filter((p) => (event ? p.event === event : isBf(p) || isBoxing(p)) && p.was_price != null && !p.was_suspect)
    .map((p) => ({ point: p, pct: Math.round((1 - p.price / (p.was_price as number)) * 100) }))
}

// Contracts / memberships / second-hand, absurd discounts, and token prices are not real discounts.
export function excludeReason(d: Discount): string | null {
  if (d.point.conditions !== '') return `带条件：${d.point.conditions}`
  if (d.pct > MAX_PCT) return `折扣超过 ${MAX_PCT}%`
  if (d.point.price < MIN_PRICE) return `价格低于 $${MIN_PRICE}`
  return null
}

export const discounts = (points: Point[], event: SaleEvent = '黑五季'): Discount[] =>
  discountCandidates(points, event).filter((d) => excludeReason(d) === null)

// Median only with at least MIN_SAMPLE rows; smaller samples report null.
export function categorySummary(ds: Discount[]) {
  return CATEGORIES.map((category) => {
    const pcts = ds.filter((d) => d.point.category === category).map((d) => d.pct)
    return { category, n: pcts.length, median: pcts.length >= MIN_SAMPLE ? median(pcts) : null }
  }).filter((c) => c.n > 0)
}

// ── Forecast (提醒价) ───────────────────────────────────────

export type Confidence = '高' | '中' | '低'
export const confidenceOf = (bfYears: number): Confidence => (bfYears >= 2 ? '高' : bfYears === 1 ? '中' : '低')

export interface Forecast {
  watch: Watch
  low: number | null
  latest: number | null
  seen26: Point | null
  newest26: Point | null
  confidence: Confidence
  earliest: string | null
  seasonMins: { year: number; point: Point }[]
  target: number | null
  targetPoint: Point | null
  range_text: string
  kw: string
}

// Broad keys mix many products, so only hand-checked (curated) points may set their numbers.
// low/latest/target/seen26 use unconditional points only (seen26 = cheapest 2026-season one, newest26 = most recent one). earliest is the first month-day (MM-DD)
// a dated BF point showed up; seasonMins are the cheapest BF points of the last two seasons.
export function forecast(watch: Watch[], points: Point[]): Forecast[] {
  return watch.map((w) => {
    const mine = points.filter((p) => p.key === w.key && (!w.broad || p.file === 'curated'))
    const plain = mine.filter((p) => p.conditions === '')
    const bfs = plain.filter(isBf)
    const lowPt = minBy(bfs)
    const low = lowPt?.price ?? null
    const lastYear = Math.max(0, ...bfs.map(yearOf))
    const latest = minBy(bfs.filter((p) => yearOf(p) === lastYear))?.price ?? null
    const seen26 = minBy(plain.filter((p) => seasonYear(p) === 2026))
    const bfYears = [...new Set(bfs.map(yearOf))].sort()
    const seasonMins = bfYears.slice(-2).map((year) => ({ year, point: minBy(bfs.filter((p) => yearOf(p) === year)) as Point }))
    const dated = bfs.filter((p) => p.date.length === 10).map((p) => p.date.slice(5)).sort()
    const newest26 = plain.filter((p) => seasonYear(p) === 2026).reduce<Point | null>((m, p) => (!m || p.date > m.date || (p.date === m.date && p.price < m.price) ? p : m), null)
    const targetPoint = [lowPt, seen26].reduce<Point | null>((m, p) => (p && (!m || p.price < m.price) ? p : m), null)
    const target = targetPoint?.price ?? null
    const range_text = low == null ? '' : latest === low ? `约 ${money(low)}` : `${money(low)} – ${money(latest as number)}`
    return { watch: w, low, latest, seen26, newest26, confidence: confidenceOf(bfYears.length), earliest: dated[0] ?? null, seasonMins, target, targetPoint, range_text, kw: target == null ? w.kw : `${w.kw} <=${Math.ceil(target)}` }
  })
}


// All price points of one watch key: count, latest price, and the newest rows.
export function keyHistory(points: Point[], key: string, limit = 30) {
  const rows = points.filter((p) => p.key === key).sort((a, b) => b.date.localeCompare(a.date))
  return { n: rows.length, latest: rows[0] ?? null, rows: rows.slice(0, limit) }
}

// ── Dates ───────────────────────────────────────────────────

export const dayNum = (iso: string) => Date.parse(iso + 'T00:00:00Z') / 86400000
export const daysBetween = (from: string, to: string) => Math.round(dayNum(to) - dayNum(from))
export const addDays = (iso: string, n: number) => new Date((dayNum(iso) + n) * 86400000).toISOString().slice(0, 10)
export const monthDay = (iso: string) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`
export const weekday = (iso: string) => '日一二三四五六'[new Date(iso + 'T00:00:00Z').getUTCDay()]

// Black Friday = day after the 4th Thursday of November.
export function blackFridayDate(year: number): number {
  const first = new Date(Date.UTC(year, 10, 1)).getUTCDay()
  return Date.UTC(year, 10, 1 + ((4 - first + 7) % 7) + 21 + 1)
}

// ── This week's checklist ───────────────────────────────────

// Steps due from today through today+7; when that is fewer than 3, the next 3 upcoming steps.
// Steps already past are dropped. `later` is every other upcoming step.
export function weekPlan(prep: PrepStep[], today: string) {
  const upcoming = prep.filter((s) => s.by >= today).sort((a, b) => a.by.localeCompare(b.by) || a.step - b.step)
  const inWeek = upcoming.filter((s) => s.by <= addDays(today, 7))
  const now = inWeek.length >= 3 ? inWeek : upcoming.slice(0, 3)
  return { now, later: upcoming.filter((s) => !now.includes(s)) }
}

// ── When BF deals appear ────────────────────────────────────

// OzBargain BF-season rows of 2024 and 2025 that carry a full date.
const ozbBfRows = (points: Point[]) =>
  points.filter((p) => isOzb(p) && isBf(p) && p.date.length === 10 && (yearOf(p) === 2024 || yearOf(p) === 2025))

// Bucket = [first offset, last offset] in days from Black Friday of that year.
const TIMING_BUCKETS: [number, number][] = [[-Infinity, -11], [-10, -10], [-9, -1], [0, 0], [1, Infinity]]

const bucketOf = (p: Point) => {
  const off = Math.round((Date.parse(p.date + 'T00:00:00Z') - blackFridayDate(yearOf(p))) / 86400000)
  return TIMING_BUCKETS.findIndex(([lo, hi]) => off >= lo && off <= hi)
}

// Percent per bucket by largest remainder, so the five numbers always add up to 100.
export function timingShares(points: Point[]) {
  const counts = TIMING_BUCKETS.map(() => 0)
  const rows = ozbBfRows(points)
  for (const p of rows) {
    counts[bucketOf(p)]++
  }
  const total = rows.length
  const exact = counts.map((n) => (total ? (n / total) * 100 : 0))
  const pct = exact.map(Math.floor)
  const order = exact.map((x, i) => [x - pct[i], i]).sort((a, b) => b[0] - a[0])
  const spare = total ? 100 - pct.reduce((a, b) => a + b, 0) : 0
  for (let k = 0; k < spare; k++) pct[order[k][1]]++
  return { total, counts, pct, beforeShare: total ? (counts[0] + counts[1] + counts[2]) / total : 0 }
}

// Median discount per timing bucket, over the same rows as timingShares that pass the outlier rules.
// `before` = buckets 1-3, `after` = buckets 4-5. A group without rows has median null.
export function timingDepth(points: Point[]) {
  const ds = discountCandidates(ozbBfRows(points), '黑五季').filter((d) => excludeReason(d) === null)
  const group = (idx: number[]) => {
    const pcts = ds.filter((d) => idx.includes(bucketOf(d.point))).map((d) => d.pct)
    return { n: pcts.length, median: pcts.length ? median(pcts) : null }
  }
  return {
    total: ds.length,
    buckets: TIMING_BUCKETS.map((_, i) => group([i])),
    before: group([0, 1, 2]),
    after: group([3, 4]),
  }
}

// ── Gift depth ──────────────────────────────────────────────

export const GIFT_BANDS = ['$50 以下 · 适合 Secret Santa', '$50–300', '$300 以上 · 大礼'] as const

export interface GiftDeal {
  key: string
  name: string
  category: string
  who: string
  pct: number
  was: number
  price: number
  year: number
  source: string
}

const bandOf = (price: number) => (price < 50 ? 0 : price < 300 ? 1 : 2)

// Best BF-season discount (any year) per gift candidate: watch rows meant as gifts plus gifts.json.
// Broad watch keys mix products, so only hand-checked (curated) points count for them.
export function giftDepth(points: Point[], watch: Watch[], gifts: Gift[]) {
  const wanted = watch.filter((w) => w.who.includes('送') || w.who.includes('Santa'))
  const watchKeys = new Set(wanted.map((w) => w.key))
  const candidates = [
    ...wanted.map((w) => ({ key: w.key, name: w.item as string | null, who: w.who, broad: !!w.broad })),
    ...gifts.filter((g) => !watchKeys.has(g.key)).map((g) => ({ key: g.key, name: null, who: g.who, broad: false })),
  ]
  const bands = GIFT_BANDS.map((title) => ({ title, items: [] as GiftDeal[] }))
  const noData: string[] = []
  for (const c of candidates) {
    const rows = points.filter((p) => p.key === c.key && isBf(p) && (!c.broad || p.file === 'curated'))
    const best = discounts(rows).reduce<Discount | null>(
      (m, d) => (m && (m.pct > d.pct || (m.pct === d.pct && m.point.date >= d.point.date)) ? m : d),
      null,
    )
    if (!best) {
      noData.push(c.name ?? c.key)
      continue
    }
    const p = best.point
    bands[bandOf(p.price)].items.push({
      key: c.key,
      name: c.name ?? p.item,
      category: p.category,
      who: c.who,
      pct: best.pct,
      was: p.was_price as number,
      price: p.price,
      year: yearOf(p),
      source: p.source,
    })
  }
  for (const b of bands) b.items.sort((a, b2) => b2.pct - a.pct)
  return { bands, noData }
}

// ── Recurring deals ─────────────────────────────────────────

export interface Recurring {
  key: string
  item: string
  category: string
  p2024: number
  p2025: number
  trend: '降价中' | '涨价了' | '差不多'
  votes: number
  source: string
}

const RECUR_MIN_PRICE = 50

const words = (s: string) => new Set(s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean))

// Same product, not a different size or model: identical digit-bearing words and word overlap >= 0.5.
export function comparableItems(a: string, b: string): boolean {
  const wa = words(a)
  const wb = words(b)
  const digits = (w: Set<string>) => [...w].filter((x) => /\d/.test(x)).sort().join('|')
  if (digits(wa) !== digits(wb)) return false
  const inter = [...wa].filter((x) => wb.has(x)).length
  return inter / new Set([...wa, ...wb]).size >= 0.5
}

// Keys with an unconditional BF price in both 2024 and 2025, 2025 minimum at least $50.
// Broad watch keys mix several products, so they never count as recurring; keys whose two yearly
// minimums are different sizes or models are dropped too.
export function recurring(points: Point[], watch: Watch[]): Recurring[] {
  const broad = new Set(watch.filter((w) => w.broad).map((w) => w.key))
  const byKey = new Map<string, Point[]>()
  for (const p of points) {
    if (broad.has(p.key) || !isBf(p) || p.conditions !== '' || p.category === '其他' || ![2024, 2025].includes(seasonYear(p))) continue
    byKey.set(p.key, [...(byKey.get(p.key) ?? []), p])
  }
  const out: Recurring[] = []
  for (const [key, rows] of byKey) {
    const min = (y: number) => minBy(rows.filter((p) => seasonYear(p) === y))
    const a = min(2024)
    const b = min(2025)
    if (!a || !b || b.price < RECUR_MIN_PRICE || !comparableItems(a.item, b.item)) continue
    out.push({
      key,
      item: b.item,
      category: b.category,
      p2024: a.price,
      p2025: b.price,
      trend: b.price < a.price * 0.95 ? '降价中' : b.price > a.price * 1.05 ? '涨价了' : '差不多',
      votes: Math.max(0, ...rows.map((p) => votesOf(p) ?? 0)),
      source: b.source,
    })
  }
  return out
}

const BRAND_STOP = new Set(['the', 'new', 'a', 'an', 'ozbargain', 'kogan'])
const BRAND_NAME: Record<string, string> = { tp: 'TP-Link', oral: 'Oral-B' }
const BRAND_MIN_ROWS = 3

// Brands (first word of the item) with at least 3 unconditional BF rows in each of 2024 and 2025.
export function recurringBrands(points: Point[], limit = 15) {
  const seen = new Map<string, { n: [number, number]; spelled: Map<string, number> }>()
  for (const p of points) {
    const y = seasonYear(p)
    if (!isBf(p) || p.conditions !== '' || (y !== 2024 && y !== 2025)) continue
    const word = p.item.trim().split(/\s+/)[0] ?? ''
    const id = word.toLowerCase()
    if (!id || BRAND_STOP.has(id) || id.startsWith('[') || id.startsWith('(')) continue
    const b = seen.get(id) ?? { n: [0, 0], spelled: new Map() }
    b.n[y - 2024]++
    b.spelled.set(word, (b.spelled.get(word) ?? 0) + 1)
    seen.set(id, b)
  }
  return [...seen]
    .filter(([, b]) => Math.min(...b.n) >= BRAND_MIN_ROWS)
    .map(([id, b]) => ({
      name: BRAND_NAME[id] ?? [...b.spelled].sort((x, y) => y[1] - x[1])[0][0],
      n: Math.min(...b.n),
    }))
    .sort((a, b) => b.n - a.n || a.name.localeCompare(b.name))
    .slice(0, limit)
}

// ── Discount depth and BF vs Boxing Day ─────────────────────

const inSeasons = (ds: Discount[]) => ds.filter((d) => [2024, 2025].includes(seasonYear(d.point)))

// Median BF discount per category over the 2024 and 2025 seasons; 其他 and categories under MIN_SAMPLE rows are dropped.
export const categoryDepth = (points: Point[]) =>
  categorySummary(inSeasons(discounts(points, '黑五季'))).flatMap((c) =>
    c.median == null || c.category === '其他' ? [] : [{ category: c.category, n: c.n, median: c.median }],
  )

// Deal counts are OzBargain-only, averaged per season; medians use every file.
export function bfVsBoxing(points: Point[]) {
  const perYear = (event: SaleEvent) =>
    points.filter((p) => isOzb(p) && p.event === event && [2024, 2025].includes(seasonYear(p))).length / 2
  const med = (event: SaleEvent) => {
    const pcts = inSeasons(discounts(points, event)).map((d) => d.pct)
    return pcts.length >= MIN_SAMPLE ? median(pcts) : null
  }
  const bf = perYear('黑五季')
  const bd = perYear('节礼日')
  return { bfPerYear: bf, bdPerYear: bd, ratio: bd > 0 ? bf / bd : null, bfMedian: med('黑五季'), bdMedian: med('节礼日') }
}

// ── Coverage (appendix) ─────────────────────────────────────

export function fileCoverage(points: Point[]) {
  return [...new Set(points.map((p) => p.file))].map((file) => {
    const mine = points.filter((p) => p.file === file)
    const years = mine.map(yearOf)
    return {
      file,
      rows: mine.length,
      bf_rows: mine.filter(isBf).length,
      boxing_rows: mine.filter(isBoxing).length,
      years: `${years.reduce((a, b) => Math.min(a, b))}–${years.reduce((a, b) => Math.max(a, b))}`,
      latest: mine.map((p) => p.retrieved_at).sort().at(-1) ?? '',
    }
  })
}
