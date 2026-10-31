// Hidden Black Friday 2026 page data. Reads ../data/bf2026 at build time (see lib/guides.ts
// for why fs/path are imported dynamically) and derives every number the page shows.

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

export interface Bf2026Data {
  points: Point[]
  promos: Promo[]
  watch: Watch[]
  calendar: CalendarEvent[]
  prep: PrepStep[]
  rules: Rule[]
  facts: Fact[]
  errors: string[]
}

// Only a missing file means "no data"; parse errors and non-arrays are reported in `errors`.
async function readJson<T>(path: string, errors: string[]): Promise<T[]> {
  const { promises: fs } = await import('fs')
  const { basename } = await import('path')
  let raw: string
  try {
    raw = await fs.readFile(path, 'utf-8')
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== 'ENOENT') errors.push(`${basename(path)}: ${String(e)}`)
    return []
  }
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows)) throw new Error('not a JSON array')
    return rows as T[]
  } catch (e) {
    errors.push(`${basename(path)}: ${e instanceof Error ? e.message : String(e)}`)
    return []
  }
}

// A bad points/promos file is skipped and reported in `errors` instead of failing the build.
async function readFolder<T>(dir: string, errors: string[]): Promise<(T & { file: string })[]> {
  const { promises: fs } = await import('fs')
  const { join } = await import('path')
  let names: string[]
  try {
    names = (await fs.readdir(dir)).filter((f) => f.endsWith('.json')).sort()
  } catch {
    return []
  }
  const lists = await Promise.all(
    names.map(async (n) => {
      const rows = await readJson<T>(join(dir, n), errors)
      return rows.map((r) => ({ ...r, file: n.replace(/\.json$/, '') }))
    }),
  )
  return lists.flat()
}

export async function loadBf2026(): Promise<Bf2026Data> {
  const { join } = await import('path')
  const { default: process } = await import('process')
  const root = join(process.cwd(), '..', 'data', 'bf2026')
  const errors: string[] = []
  const [points, promos, watch, calendar, prep, rules, facts] = await Promise.all([
    readFolder<Omit<Point, 'file'>>(join(root, 'points'), errors),
    readFolder<Omit<Promo, 'file'>>(join(root, 'promos'), errors),
    readJson<Watch>(join(root, 'watch.json'), errors),
    readJson<CalendarEvent>(join(root, 'calendar.json'), errors),
    readJson<PrepStep>(join(root, 'prep.json'), errors),
    readJson<Rule>(join(root, 'rules.json'), errors),
    readJson<Fact>(join(root, 'facts.json'), errors),
  ])
  return { points, promos, watch, calendar, prep, rules, facts, errors }
}

// ── Formatting ──────────────────────────────────────────────

export function money(n: number): string {
  const whole = Number.isInteger(n)
  return '$' + n.toLocaleString('en-AU', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 })
}

// ── Derivations (pure) ──────────────────────────────────────

export const isBf = (p: Point) => p.event === '黑五季'
export const isBoxing = (p: Point) => p.event === '节礼日'
export type SaleEvent = '黑五季' | '节礼日'

// A January Boxing Day sale belongs to the season that started the December before.
export const seasonYear = (p: Point) => (isBoxing(p) && p.date.slice(5, 7) === '01' ? yearOf(p) - 1 : yearOf(p))
export const yearOf = (p: Point) => Number(p.date.slice(0, 4))

const minBy = (ps: Point[]): Point | null => ps.reduce<Point | null>((m, p) => (m && m.price <= p.price ? m : p), null)

function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2)
}

export interface Discount {
  point: Point
  pct: number
}

export function discounts(points: Point[], event: SaleEvent = '黑五季'): Discount[] {
  return points
    .filter((p) => p.event === event && p.was_price != null && !p.was_suspect)
    .map((p) => ({ point: p, pct: Math.round((1 - p.price / (p.was_price as number)) * 100) }))
}

export function categorySummary(ds: Discount[]) {
  return CATEGORIES.map((category) => {
    const pcts = ds.filter((d) => d.point.category === category).map((d) => d.pct)
    return { category, n: pcts.length, median: pcts.length ? median(pcts) : null }
  }).filter((c) => c.n > 0)
}

export interface CompareRow {
  key: string
  item: string
  bf: Point
  other: Point | null
  beaten: boolean
  premium_pct: number | null
}

export function compare(points: Point[]): CompareRow[] {
  const keys = [...new Set(points.map((p) => p.key))]
  const rows: CompareRow[] = []
  for (const key of keys) {
    const mine = points.filter((p) => p.key === key)
    const bfs = mine.filter(isBf)
    const others = mine.filter((p) => !isBf(p))
    if (!bfs.length || !(others.length || bfs.some((p) => p.history_low))) continue
    const bf = minBy(bfs) as Point
    const other = minBy(others)
    rows.push({
      key,
      item: bf.item,
      bf,
      other,
      beaten: other != null && other.price < bf.price,
      premium_pct: other ? Math.round((bf.price / other.price - 1) * 100) : null,
    })
  }
  return rows.sort((a, b) => Number(b.beaten) - Number(a.beaten) || (b.premium_pct ?? -1) - (a.premium_pct ?? -1))
}

export interface BoxingRow {
  key: string
  item: string
  bf: Point
  bd: Point
  boxing_cheaper: boolean
  saving_pct: number
}

export function bfVsBoxing(points: Point[]): BoxingRow[] {
  const rows: BoxingRow[] = []
  for (const key of new Set(points.map((p) => p.key))) {
    const mine = points.filter((p) => p.key === key)
    const bf = minBy(mine.filter(isBf))
    const bd = minBy(mine.filter(isBoxing))
    if (!bf || !bd) continue
    rows.push({ key, item: bf.item, bf, bd, boxing_cheaper: bd.price < bf.price, saving_pct: Math.round((1 - bd.price / bf.price) * 100) })
  }
  return rows.sort((a, b) => Number(b.boxing_cheaper) - Number(a.boxing_cheaper) || b.saving_pct - a.saving_pct)
}

export function headline(ds: Discount[], cmp: CompareRow[]) {
  return {
    n_deals: ds.length,
    median_pct: ds.length ? median(ds.map((d) => d.pct)) : 0,
    n_compare: cmp.length,
    n_beaten: cmp.filter((c) => c.beaten).length,
  }
}

export interface Forecast {
  watch: Watch
  low: number | null
  latest: number | null
  seen26: Point | null
  target: number | null
  range_text: string
  kw: string
}

// low/latest/target use unconditional points only; seen26 is the cheapest 2026 point of any kind.
export function forecast(watch: Watch[], points: Point[]): Forecast[] {
  return watch.map((w) => {
    const mine = points.filter((p) => p.key === w.key)
    const plain = mine.filter((p) => p.conditions === '')
    const bfs = plain.filter(isBf)
    const low = minBy(bfs)?.price ?? null
    const lastYear = Math.max(0, ...bfs.map(yearOf))
    const latest = minBy(bfs.filter((p) => yearOf(p) === lastYear))?.price ?? null
    const seen26 = minBy(mine.filter((p) => seasonYear(p) === 2026))
    const plain26 = minBy(plain.filter((p) => seasonYear(p) === 2026))
    const candidates = [low, plain26?.price ?? null].filter((n): n is number => n != null)
    const target = candidates.length ? Math.min(...candidates) : null
    const range_text = low == null ? '' : latest === low ? `约 ${money(low)}` : `${money(low)} – ${money(latest as number)}`
    return { watch: w, low, latest, seen26, target, range_text, kw: target == null ? w.kw : `${w.kw} <=${Math.ceil(target)}` }
  })
}

export function topVoted(points: Point[]) {
  return CATEGORIES.map((category) => ({
    category,
    points: points
      .filter((p) => isBf(p) && p.votes != null && p.category === category)
      .sort((a, b) => (b.votes as number) - (a.votes as number))
      .slice(0, 5),
  })).filter((c) => c.points.length > 0)
}

export function coverage(points: Point[], watch: Watch[]) {
  const files = [...new Set(points.map((p) => p.file))].map((file) => {
    const mine = points.filter((p) => p.file === file)
    const years = mine.map(yearOf)
    return {
      file,
      rows: mine.length,
      bf_rows: mine.filter(isBf).length,
      years: `${Math.min(...years)}–${Math.max(...years)}`,
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
