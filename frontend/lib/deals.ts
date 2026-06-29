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
  votesPos: number
  commentCount: number
  hotScore: number
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

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export async function getLiveDeals(): Promise<LiveDeal[]> {
  const now = new Date()
  const today = isoDate(now)
  const yesterday = isoDate(new Date(now.getTime() - 86_400_000))

  const [todayRows, yestRows] = await Promise.all([
    readObservationsFile(today),
    readObservationsFile(yesterday),
  ])

  const all = [...todayRows, ...yestRows]
  if (!all.length) return []

  // Find the exact timestamp of the most recent scan batch. All rows in one
  // batch share an identical ts string, so an exact match gives us one batch only.
  const maxTs = all.reduce((m, r) => (r.ts > m ? r.ts : m), '')
  const batch = all.filter((r) => r.ts === maxTs)

  const hot = batch.filter((r) => r.is_hot === true)

  return hot
    .map((r) => ({
      key: r.deal_key as string,
      title: r.title as string,
      url: dealUrl(r.deal_key as string),
      source: (r.deal_key as string).split(':')[0],
      price: r.price && r.price > 0 ? (r.price as number) : null,
      discountPercent: r.discount_percent ? (r.discount_percent as number) : null,
      votesPos: r.votes_pos as number,
      commentCount: r.comment_count as number,
      hotScore: r.hot_score as number,
      hotLevel: (r.hot_level as string | null) ?? null,
      ageHours: r.age_hours as number,
      ts: r.ts as string,
    }))
    .sort((a, b) => b.hotScore - a.hotScore)
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
