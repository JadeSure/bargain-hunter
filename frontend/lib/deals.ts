// Reads hot deals from the observations JSONL files produced by the pipeline.
// Called at build time (Next.js static generation) — uses fs/path/process via
// dynamic imports so this module stays loadable on the edge runtime (returns []
// gracefully if the files are unavailable, mirroring the pattern in lib/guides.ts).

export interface LiveDeal {
  key: string
  title: string
  url: string
  source: 'ozbargain' | 'camelcamelcamel' | string
  price: number | null
  discountPercent: number | null
  isFree: boolean
  votesPos: number
  commentCount: number
  hotScore: number
  peakScore: number
  hotLevel: string | null
  ageHours: number
  ts: string
}

function dealUrl(key: string): string {
  const colon = key.indexOf(':')
  const source = key.slice(0, colon)
  const id = key.slice(colon + 1)
  if (source === 'ozbargain') return `https://www.ozbargain.com.au/node/${id}`
  if (source === 'camelcamelcamel') return `https://au.camelcamelcamel.com/product/${id}`
  return '#'
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function readObservationsFile(date: string): Promise<any[]> {
  try {
    const { promises: fs } = await import('fs')
    const { join } = await import('path')
    const { default: process } = await import('process')
    const p = join(process.cwd(), '..', 'data', 'observations', `${date}.jsonl`)
    const content = await fs.readFile(p, 'utf-8')
    return content
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

// Safety cap: a deal stays on the page as long as it is still active (present in
// the latest scan batch), up to this many hours after it was last flagged hot.
// In practice most OzBargain deals expire/sell out within a day or two and drop
// off via the still-active guard; this cap just stops a rare evergreen deal from
// lingering for weeks. Expired/out-of-stock deals drop off immediately regardless.
const RETENTION_HOURS = 72

// Hot tiers ranked so the higher value wins when picking a deal's peak level.
const LEVEL_RANK: Record<string, number> = { top: 3, great: 2, good: 1 }

type ObsRow = Awaited<ReturnType<typeof readObservationsFile>>[number]

function aetDate(d: Date): string {
  // Observation files are named by Australia/Sydney (AET) date (see
  // observations.py's flush()), so resolve filenames in AET — not UTC, which
  // would point at the wrong file for up to ~11h around the date boundary.
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Australia/Sydney' }).format(d)
}

export async function getLiveDeals(): Promise<LiveDeal[]> {
  const now = new Date()

  // Read enough AET-dated day files to cover the retention window (plus one for
  // the date-boundary). Files are named by Australia/Sydney date, so we walk
  // back day by day from today in AET.
  const DAY_MS = 86_400_000
  const fileCount = Math.ceil(RETENTION_HOURS / 24) + 1
  const dates = Array.from({ length: fileCount }, (_, i) =>
    aetDate(new Date(now.getTime() - i * DAY_MS)),
  )
  const fileRows = await Promise.all(dates.map(readObservationsFile))

  const all = fileRows.flat()
  if (!all.length) return []

  // Retain a deal for RETENTION_HOURS after it was last hot, so good deals don't
  // vanish the moment their vote-velocity spike passes. Per deal we track the
  // latest observation (for current score + stats) and the peak level ever
  // classified by the pipeline (stable badge that doesn't decay with age).
  const cutoffMs = now.getTime() - RETENTION_HOURS * 3_600_000

  interface Agg {
    latest: ObsRow
    peakLevel: string | null  // highest tier ever classified (badge, stable)
    peakScore: number         // highest hot_score ever seen (for display)
    lastHotTs: string
  }
  const byKey = new Map<string, Agg>()

  for (const r of all) {
    const tsMs = Date.parse(r.ts as string)
    if (Number.isNaN(tsMs) || tsMs < cutoffMs) continue
    const key = r.deal_key as string
    let agg = byKey.get(key)
    if (!agg) {
      agg = { latest: r, peakLevel: null, peakScore: 0, lastHotTs: '' }
      byKey.set(key, agg)
    }
    if ((r.ts as string) > (agg.latest.ts as string)) agg.latest = r
    if (r.is_hot === true) {
      if ((r.ts as string) > agg.lastHotTs) agg.lastHotTs = r.ts as string
      const score = (r.hot_score as number) ?? 0
      if (score > agg.peakScore) {
        agg.peakScore = score
        agg.peakLevel = (r.hot_level as string | null) ?? null  // level at peak score
      }
    }
  }

  const entries: { deal: LiveDeal }[] = []
  for (const [key, agg] of byKey) {
    if (!agg.lastHotTs || !agg.peakLevel) continue // never hot within the window
    if (agg.peakLevel === 'good') continue          // only show top and great
    const r = agg.latest
    entries.push({
      deal: {
        key,
        title: r.title as string,
        url: dealUrl(key),
        source: key.split(':')[0],
        isFree: /^\s*free\b/i.test(r.title as string),
        price: /^\s*free\b/i.test(r.title as string) ? null : (r.price && r.price > 0 ? (r.price as number) : null),
        discountPercent: /^\s*free\b/i.test(r.title as string) ? null : (r.discount_percent ? (r.discount_percent as number) : null),
        votesPos: r.votes_pos as number,
        commentCount: r.comment_count as number,
        hotScore: (r.hot_score as number) ?? 0,  // current score (reflects actual heat now)
        peakScore: agg.peakScore,                  // highest score ever seen in retention window
        hotLevel: agg.peakLevel,                  // peak level badge (stable, doesn't decay)
        ageHours: r.age_hours as number,
        ts: r.ts as string,
      },
    })
  }

  // Highest tier first (Top > Great > Good); within a tier, by peak score.
  entries.sort((a, b) => {
    const ra = a.deal.hotLevel ? (LEVEL_RANK[a.deal.hotLevel] ?? 0) : 0
    const rb = b.deal.hotLevel ? (LEVEL_RANK[b.deal.hotLevel] ?? 0) : 0
    if (ra !== rb) return rb - ra
    return b.deal.peakScore - a.deal.peakScore
  })

  return entries.map((e) => e.deal)
}

export function formatAge(ageHours: number): string {
  if (ageHours < 1) return `${Math.round(ageHours * 60)}m ago`
  if (ageHours < 24) return `${Math.round(ageHours)}h ago`
  return `${Math.round(ageHours / 24)}d ago`
}

export function sourceLabel(source: string): string {
  if (source === 'ozbargain') return 'OzBargain'
  if (source === 'camelcamelcamel') return 'CamelCamelCamel'
  return source
}
