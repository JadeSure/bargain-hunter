// Pure data types and derivations for the hidden BF 2026 page. No fs, no relative imports:
// the client explorer and the node selftest both import this file directly.

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

export interface Bf2026Data {
  points: Point[]
  promos: Promo[]
  watch: Watch[]
  calendar: CalendarEvent[]
  prep: PrepStep[]
  rules: Rule[]
  facts: Fact[]
  signals: Signal[]
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
// Shopping year Y runs Y-06-01 .. (Y+1)-05-31 (EOFY, Prime Day, Click Frenzy, BF, Boxing Day).
export const shopYear = (p: Point) => (Number(p.date.slice(5, 7)) >= 6 ? yearOf(p) : yearOf(p) - 1)

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

export function excludedDiscounts(points: Point[]): (Discount & { reason: string })[] {
  return discountCandidates(points).flatMap((d) => {
    const reason = excludeReason(d)
    return reason ? [{ ...d, reason }] : []
  })
}

// Median only with at least MIN_SAMPLE rows; smaller samples report null ("样本不足").
export function categorySummary(ds: Discount[]) {
  return CATEGORIES.map((category) => {
    const pcts = ds.filter((d) => d.point.category === category).map((d) => d.pct)
    return { category, n: pcts.length, median: pcts.length >= MIN_SAMPLE ? median(pcts) : null }
  }).filter((c) => c.n > 0)
}

export const overallMedian = (ds: Discount[]): number | null => (ds.length >= MIN_SAMPLE ? median(ds.map((d) => d.pct)) : null)

// Rows with votes first (most votes first), then the rest by discount.
export function rankDeals(ds: Discount[]): Discount[] {
  return [...ds].sort((a, b) => {
    const va = votesOf(a.point)
    const vb = votesOf(b.point)
    if ((va != null) !== (vb != null)) return va != null ? -1 : 1
    if (va != null && vb != null && va !== vb) return vb - va
    return b.pct - a.pct
  })
}

// ── Comparable-item guard ───────────────────────────────────

const tokens = (s: string) => new Set(s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean))

// ponytail: compares only the two min rows' item strings (same digit-bearing tokens, Jaccard >= 0.5);
// the proper fix is canonical product keys in the data.
export function comparableItems(a: string, b: string): boolean {
  const ta = tokens(a)
  const tb = tokens(b)
  const digits = (t: Set<string>) => [...t].filter((x) => /\d/.test(x)).sort().join('|')
  if (digits(ta) !== digits(tb)) return false
  const inter = [...ta].filter((x) => tb.has(x)).length
  const union = new Set([...ta, ...tb]).size
  return union > 0 && inter / union >= 0.5
}

// ── Compare (same shopping year) and BF vs Boxing Day ───────

export interface Side {
  item: string
  price: number
  date: string
  event: string
  retailer: string
  file: string
  votes: number | null
  source: string
  note: string
}

const sideOf = (p: Point): Side => ({
  item: p.item,
  price: p.price,
  date: p.date,
  event: p.event,
  retailer: p.retailer,
  file: p.file,
  votes: votesOf(p),
  source: p.source,
  note: p.note,
})

export interface ComparePair {
  key: string
  category: string
  year: number
  bf: Side
  other: Side
  beaten: boolean
  premium_pct: number
  comparable: boolean
}

const byKey = (points: Point[]) => {
  const m = new Map<string, Point[]>()
  for (const p of points) if (p.conditions === '') m.set(p.key, [...(m.get(p.key) ?? []), p])
  return m
}

// BF season Y's cheapest price against the cheapest non-BF price inside shopping year Y.
export function comparePairs(points: Point[]): ComparePair[] {
  const out: ComparePair[] = []
  for (const [key, rows] of byKey(points)) {
    const bfs = rows.filter(isBf)
    for (const year of new Set(bfs.map(yearOf))) {
      const bf = minBy(bfs.filter((p) => yearOf(p) === year))
      const other = minBy(rows.filter((p) => !isBf(p) && shopYear(p) === year))
      if (!bf || !other) continue
      out.push({
        key,
        category: bf.category,
        year,
        bf: sideOf(bf),
        other: sideOf(other),
        beaten: other.price < bf.price,
        premium_pct: Math.round((bf.price / other.price - 1) * 100),
        comparable: comparableItems(bf.item, other.item),
      })
    }
  }
  return out.sort((a, b) => Number(b.beaten) - Number(a.beaten) || b.premium_pct - a.premium_pct)
}

export interface BoxingPair {
  key: string
  category: string
  year: number
  bf: Side
  bd: Side
  boxing_cheaper: boolean
  saving_pct: number
  comparable: boolean
}

// BF season Y against Boxing Day season Y (January counts toward the previous year).
export function boxingPairs(points: Point[]): BoxingPair[] {
  const out: BoxingPair[] = []
  for (const [key, rows] of byKey(points)) {
    const bfs = rows.filter(isBf)
    const bds = rows.filter(isBoxing)
    for (const year of new Set(bfs.map(yearOf))) {
      const bf = minBy(bfs.filter((p) => yearOf(p) === year))
      const bd = minBy(bds.filter((p) => seasonYear(p) === year))
      if (!bf || !bd) continue
      out.push({
        key,
        category: bf.category,
        year,
        bf: sideOf(bf),
        bd: sideOf(bd),
        boxing_cheaper: bd.price < bf.price,
        saving_pct: Math.round((1 - bd.price / bf.price) * 100),
        comparable: comparableItems(bf.item, bd.item),
      })
    }
  }
  return out.sort((a, b) => Number(b.boxing_cheaper) - Number(a.boxing_cheaper) || b.saving_pct - a.saving_pct)
}

// Distinct product keys whose pair failed the comparable-item guard.
export const suspectCount = (pairs: { key: string; comparable: boolean }[]) =>
  new Set(pairs.filter((p) => !p.comparable).map((p) => p.key)).size

// ── Filters (shared by the client explorer) ─────────────────

export interface Filters {
  cats: string[]
  year: number | null
  file: string | null
  minVotes: number
}

const votesOk = (votes: number | null, f: Filters) => votes == null || votes >= f.minVotes

export function pairPasses(
  p: { category: string; year: number; sides: { file: string; votes: number | null }[] },
  f: Filters,
): boolean {
  return (
    f.cats.includes(p.category) &&
    (f.year == null || p.year === f.year) &&
    (f.file == null || p.sides.some((s) => s.file === f.file)) &&
    p.sides.every((s) => votesOk(s.votes, f))
  )
}

// ── Headline ────────────────────────────────────────────────

export function headline(points: Point[]) {
  const bf = discounts(points, '黑五季')
  const bd = discounts(points, '节礼日')
  const cmp = comparePairs(points).filter((c) => c.comparable)
  const box = boxingPairs(points).filter((c) => c.comparable)
  return {
    bf,
    bd,
    bf_median: overallMedian(bf),
    bd_median: overallMedian(bd),
    n_compare: cmp.length,
    n_beaten: cmp.filter((c) => c.beaten).length,
    n_boxing: box.length,
    n_boxing_cheaper: box.filter((c) => c.boxing_cheaper).length,
  }
}

// ── Forecast (提醒价) ───────────────────────────────────────

export interface Forecast {
  watch: Watch
  low: number | null
  latest: number | null
  seen26: Point | null
  target: number | null
  targetPoint: Point | null
  range_text: string
  kw: string
}

// Broad keys mix many products, so only hand-checked (curated) points may set their numbers.
// low/latest/target use unconditional points only; seen26 is the cheapest 2026-season point.
export function forecast(watch: Watch[], points: Point[]): Forecast[] {
  return watch.map((w) => {
    const mine = points.filter((p) => p.key === w.key && (!w.broad || p.file === 'curated'))
    const plain = mine.filter((p) => p.conditions === '')
    const bfs = plain.filter(isBf)
    const lowPt = minBy(bfs)
    const low = lowPt?.price ?? null
    const lastYear = Math.max(0, ...bfs.map(yearOf))
    const latest = minBy(bfs.filter((p) => yearOf(p) === lastYear))?.price ?? null
    const seen26 = minBy(mine.filter((p) => seasonYear(p) === 2026))
    const plain26 = minBy(plain.filter((p) => seasonYear(p) === 2026))
    const targetPoint = [lowPt, plain26].reduce<Point | null>((m, p) => (p && (!m || p.price < m.price) ? p : m), null)
    const target = targetPoint?.price ?? null
    const range_text = low == null ? '' : latest === low ? `约 ${money(low)}` : `${money(low)} – ${money(latest as number)}`
    return { watch: w, low, latest, seen26, target, targetPoint, range_text, kw: target == null ? w.kw : `${w.kw} <=${Math.ceil(target)}` }
  })
}

// All price points of one watch key: count, latest price, and the newest rows.
export function keyHistory(points: Point[], key: string, limit = 30) {
  const rows = points.filter((p) => p.key === key).sort((a, b) => b.date.localeCompare(a.date))
  return { n: rows.length, latest: rows[0] ?? null, rows: rows.slice(0, limit) }
}

// ── Timing (daily count of new deals around the sale) ───────

// Black Friday = day after the 4th Thursday of November.
export function blackFridayDate(year: number): number {
  const first = new Date(Date.UTC(year, 10, 1)).getUTCDay()
  return Date.UTC(year, 10, 1 + ((4 - first + 7) % 7) + 21 + 1)
}

export interface TimingDay {
  off: number
  n: number
  hot: number
}

export function timing(points: Point[], event: SaleEvent, lo: number, hi: number) {
  const years = [...new Set(points.filter((p) => p.event === event).map(seasonYear))].sort()
  return years.map((year) => {
    const anchor = event === '黑五季' ? blackFridayDate(year) : Date.UTC(year, 11, 26)
    const days: TimingDay[] = []
    for (let off = lo; off <= hi; off++) days.push({ off, n: 0, hot: 0 })
    for (const p of points) {
      if (p.event !== event || seasonYear(p) !== year || p.date.length !== 10) continue
      const off = Math.round((Date.parse(p.date + 'T00:00:00Z') - anchor) / 86400000)
      if (off < lo || off > hi) continue
      const d = days[off - lo]
      d.n++
      if ((votesOf(p) ?? 0) >= 50) d.hot++
    }
    return { year, days, total: days.reduce((s, d) => s + d.n, 0) }
  }).filter((t) => t.total > 0)
}

// ── Coverage ────────────────────────────────────────────────

export function coverage(points: Point[], watch: Watch[]) {
  const files = [...new Set(points.map((p) => p.file))].map((file) => {
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
  const keys = watch.map((w) => {
    const mine = points.filter((p) => p.key === w.key)
    return {
      key: w.key,
      item: w.item,
      bf_years: new Set(mine.filter(isBf).map(yearOf)).size,
      boxing_years: new Set(mine.filter(isBoxing).map(seasonYear)).size,
      non_bf: mine.filter((p) => !isBf(p)).length,
      retailers_2026: new Set(mine.filter((p) => seasonYear(p) === 2026 && p.retailer).map((p) => p.retailer)).size,
    }
  })
  return { files, keys }
}
