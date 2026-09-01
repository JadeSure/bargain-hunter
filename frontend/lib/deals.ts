// Reads hot deals from the observations JSONL files produced by the pipeline.
// Called at build time (Next.js static generation) — uses fs/path/process via
// dynamic imports so this module stays loadable on the edge runtime (returns []
// gracefully if the files are unavailable, mirroring the pattern in lib/guides.ts).

export interface LiveDeal {
  key: string
  title: string
  description: string | null
  url: string
  source: 'ozbargain' | 'camelcamelcamel' | string
  currency: string
  price: number | null
  discountPercent: number | null
  cashbackPercent: number | null
  priceRank: 'lowest' | 'low' | 'typical' | 'high' | null
  isFree: boolean
  votesPos: number
  commentCount: number
  hotScore: number
  peakScore: number
  hotLevel: string | null
  ageHours: number
  ts: string
}

// Checked on the small number of currently-displayed deals to catch status
// changes the observation log cannot see until the next successful scan.
const OZB_INACTIVE_STATUSES = new Set([404, 410])
const OZB_INACTIVE_MARKERS = [
  /\bnodeexpiry\b[^"]*\bexpired\b/i,
  /\bnode-ozbdeal\b[^"]*\bexpired\b/i,
  /<span class="expired">(?:expired|out of stock)<\/span>/i,
  /\bnode-unpublished\b/i,
  /<div class="messages[^"]*"[^>]*>[\s\S]{0,500}\bunpublished\b/i,
  /\bthis (?:deal|post) has been unpublished\b/i,
]
const OZB_USER_AGENT =
  'bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)'

async function isOzbargainInactive(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(6000),
      headers: { 'User-Agent': OZB_USER_AGENT },
    })
    if (OZB_INACTIVE_STATUSES.has(res.status)) return true
    if (!res.ok) return false // fail open — a transient fetch error shouldn't hide a live deal
    const html = await res.text()
    return OZB_INACTIVE_MARKERS.some((marker) => marker.test(html))
  } catch {
    return false // fail open — network hiccups shouldn't hide a live deal
  }
}

function sourceFromKey(key: string): string {
  return key.split(':', 1)[0]
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
function resolveUrl(key: string, r: any): string {
  // The new sources' deal_id is a hash of the feed guid, so unlike ozbargain/
  // camelcamelcamel there is no way to reconstruct their URL from the key —
  // it has to be the observation row's stored `url` (added alongside
  // `currency`). Rows recorded before that field existed fall back to
  // dealUrl(key), which is '#' for those sources; callers must drop those.
  return (r.url as string) || dealUrl(key)
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function readObservationsFile(date: string): Promise<any[]> {
  const { promises: fs } = await import('fs')
  const { join } = await import('path')
  const { default: process } = await import('process')
  const dir = join(process.cwd(), '..', 'data', 'observations')

  // maintain-obs gzips each day file once it's no longer today's AET date
  // (see src/bargain_hunter/observations.py), so most of RETENTION_HOURS'
  // 72h window lives in `.gz`, not `.jsonl`. Try plain first, then gunzip.
  let content: string
  try {
    content = await fs.readFile(join(dir, `${date}.jsonl`), 'utf-8')
  } catch {
    try {
      const { gunzipSync } = await import('zlib')
      const gz = await fs.readFile(join(dir, `${date}.jsonl.gz`))
      content = gunzipSync(gz).toString('utf-8')
    } catch (err: unknown) {
      // A missing day inside the retention window is normal (neither file
      // exists) and must stay silent; anything else — corrupt gzip, bad
      // permissions — should not fail silently like the missing .gz support
      // did for two days in production.
      if ((err as NodeJS.ErrnoException)?.code !== 'ENOENT') {
        console.error(`readObservationsFile: ${date} unreadable`, err)
      }
      return []
    }
  }

  try {
    return content.split('\n').filter(Boolean).map((line) => JSON.parse(line))
  } catch (err) {
    console.error(`readObservationsFile: ${date} failed to parse`, err)
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

// These sources are differs: they emit a Deal once, at the moment a price/rate
// change is detected, then never re-emit it. isStillInLatestSourceBatch would
// expire them the moment the source's next fetch happens (as little as a day
// later), so they skip that gate and rely on the 72h RETENTION_HOURS window
// alone. Every other new source re-emits every poll, so the batch gate is
// correct for them.
// Sources switched off in config/settings.yaml. The 72h retention window
// exists so a good deal doesn't vanish the moment its spike passes — but a
// source that was deliberately disabled is a different thing, and without this
// its cards linger on the board for three days after the decision. Keep in
// sync with `enabled: false` entries in settings.yaml.
const RETIRED_SOURCES = new Set(['smzdm'])

const EVENT_EMITTING_SOURCES = new Set(['openrouter', 'bank_rates', 'cn_llm_docs', 'free_llm'])

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
  const latestTsBySource = new Map<string, string>()

  for (const r of all) {
    const tsMs = Date.parse(r.ts as string)
    if (Number.isNaN(tsMs) || tsMs < cutoffMs) continue
    const key = r.deal_key as string
    const source = sourceFromKey(key)
    const ts = r.ts as string
    const latestSourceTs = latestTsBySource.get(source)
    if (!latestSourceTs || ts > latestSourceTs) latestTsBySource.set(source, ts)
    let agg = byKey.get(key)
    if (!agg) {
      agg = { latest: r, peakLevel: null, peakScore: 0, lastHotTs: '' }
      byKey.set(key, agg)
    }
    if (ts > (agg.latest.ts as string)) agg.latest = r
    if (r.is_hot === true) {
      if (ts > agg.lastHotTs) agg.lastHotTs = ts
      const score = (r.hot_score as number) ?? 0
      if (score > agg.peakScore) {
        agg.peakScore = score
        agg.peakLevel = (r.hot_level as string | null) ?? null  // level at peak score
      }
    }
  }

  // A deal that has scrolled out of its source feed stops being re-observed, so
  // its stored age_hours freezes at last sighting. posted_at is fixed, though,
  // and recoverable as (observation ts − age at that observation) — recompute
  // against *now* so the card shows how long it's really been up, not a stale
  // value. For a still-in-feed deal this just adds the minutes since last scan.
  function liveAgeHours(r: ObsRow): number {
    const stored = r.age_hours as number | null
    if (stored == null || Number.isNaN(stored)) return stored as number
    const tsMs = Date.parse(r.ts as string)
    if (Number.isNaN(tsMs)) return stored
    const postedMs = tsMs - stored * 3_600_000
    return Math.max((now.getTime() - postedMs) / 3_600_000, 0)
  }

  function toEntries(candidates: [string, Agg][]): { deal: LiveDeal }[] {
    return candidates.map(([key, agg]) => {
      const r = agg.latest
      return {
        deal: {
          key,
          title: r.title as string,
          // Rows recorded before observations.py stored `description` have no
          // such key; null renders nothing rather than "undefined".
          description: (r.description as string | null) ?? null,
          url: resolveUrl(key, r),
          source: sourceFromKey(key),
          currency: (r.currency as string) ?? 'AUD',
          isFree: /^\s*free\b/i.test(r.title as string),
          price: /^\s*free\b/i.test(r.title as string) ? null : (r.price && r.price > 0 ? (r.price as number) : null),
          discountPercent: /^\s*free\b/i.test(r.title as string) ? null : (r.discount_percent ? (r.discount_percent as number) : null),
          cashbackPercent: r.cashback_percent ? (r.cashback_percent as number) : null,
          priceRank: (r.price_rank as LiveDeal['priceRank']) ?? null,
          votesPos: r.votes_pos as number,
          commentCount: r.comment_count as number,
          hotScore: (r.hot_score as number) ?? 0,  // current score (reflects actual heat now)
          peakScore: agg.peakScore,                  // highest score ever seen in retention window
          hotLevel: agg.peakLevel,                  // peak level badge (stable, doesn't decay)
          ageHours: liveAgeHours(r),
          ts: r.ts as string,
        },
      }
    })
  }

  function isStillInLatestSourceBatch(key: string, agg: Agg): boolean {
    return (agg.latest.ts as string) === latestTsBySource.get(sourceFromKey(key))
  }

  // Drop deals OzBargain itself now shows as expired/unpublished, even within
  // the retention window — only a handful of deals are ever checked here.
  async function keepLive(entries: { deal: LiveDeal }[]): Promise<{ deal: LiveDeal }[]> {
    const inactive = await Promise.all(
      entries.map((e) => (
        e.deal.source === 'ozbargain' ? isOzbargainInactive(e.deal.url) : false
      )),
    )
    return entries.filter((_, i) => !inactive[i])
  }

  // Top-tier deals are the main event, but top-tier supply is bursty (it
  // clusters around big sale days, e.g. EOFY) and a single stray top-tier
  // classification (e.g. a non-expiring news/policy post that racked up
  // votes) shouldn't be able to crowd out every genuinely good "great" deal.
  // So: always show live top-tier deals, and top up with the best "great"
  // deals (by peak score) whenever the live count is thin, rather than an
  // all-or-nothing top-vs-great choice. The fallback check happens AFTER the
  // live-expiry filter, not on the raw candidate count, so a page that would
  // otherwise render few live top deals (even if some are still technically
  // inside the retention window) still gets topped up.
  const FALLBACK_GREAT_LIMIT = 8
  const MIN_DISPLAY_COUNT = 6
  // The AU tier ladder above is bounded by vote velocity; the new-source
  // sections below have no such signal, and some (Slickdeals' 6 keyword
  // queries alone) return 100+ items per fetch. Cap each rendered section
  // (Australia — banking & travel / North America / China / LLM token
  // prices) the same way, so the board stays a curated page, not a dump.
  // Do not remove this — it exists because these sources emit in bulk.
  const NEW_SOURCE_SECTION_CAP = 12
  // These feeds surface evergreen/reposted content that can be weeks old even
  // when freshly observed (HIGH_VALUE_SOURCES_PLAN.md notes DealNews items
  // "date to February"). RETENTION_HOURS bounds observation recency, not the
  // deal's own age, so a month-old repost can otherwise sit on the board
  // indefinitely. 7 days keeps the bulk of real content while dropping what
  // reads as stale. AU tier ladder is unaffected — it's bounded by vote data.
  const NEW_SOURCE_MAX_AGE_HOURS = 24 * 7

  const topCandidates: [string, Agg][] = []
  const greatCandidates: [string, Agg][] = []
  for (const entry of byKey) {
    const [key, agg] = entry
    if (!agg.lastHotTs || !agg.peakLevel) continue // never hot within the window
    // Once hot, keep an ozbargain deal for the full RETENTION_HOURS as long as
    // it's still live — leaving the /deals/feed batch (pushed out by newer
    // posts) is NOT the same as expiring, and the "retain 72h while still
    // active" rule (commit 8a489be6) meant *active*, not *still in the feed*.
    // keepLive's isOzbargainInactive() fetch below is the real still-active
    // check. camelcamelcamel has no such live check, so it keeps the batch gate.
    if (sourceFromKey(key) !== 'ozbargain' && !isStillInLatestSourceBatch(key, agg)) continue
    if (agg.peakLevel === 'top') topCandidates.push(entry)
    else if (agg.peakLevel === 'great') greatCandidates.push(entry)
  }

  let live = await keepLive(toEntries(topCandidates))
  if (live.length < MIN_DISPLAY_COUNT) {
    const greatEntries = toEntries(
      greatCandidates.sort((a, b) => b[1].peakScore - a[1].peakScore).slice(0, FALLBACK_GREAT_LIMIT),
    )
    const greatLive = await keepLive(greatEntries)
    live = [...live, ...greatLive]
  }

  // Highest tier first (Top > Great > Good); within a tier, by peak score.
  live.sort((a, b) => {
    const ra = a.deal.hotLevel ? (LEVEL_RANK[a.deal.hotLevel] ?? 0) : 0
    const rb = b.deal.hotLevel ? (LEVEL_RANK[b.deal.hotLevel] ?? 0) : 0
    if (ra !== rb) return rb - ra
    return b.deal.peakScore - a.deal.peakScore
  })

  // Newer voteless sources (bank_rates, iknowthepilot, dealnews, slickdeals,
  // v2ex, openrouter) reach a subscriber via the watch track, not vote
  // velocity, so is_hot/peakLevel above rarely fires for them — gating on it
  // like the AU tier ladder would keep the board empty. Keep them on recency
  // instead: any deal still within RETENTION_HOURS (byKey only holds those)
  // that is still in its own source's latest scan batch. ozbargain/
  // camelcamelcamel are excluded here since they're already handled above.
  // Grouped by rendered section (region, minus the AU tier-ladder sources
  // already handled above) so the cap applies per section, not globally —
  // North America shouldn't starve China just because Slickdeals is noisy.
  const recencyBySection = new Map<DealRegion, [string, Agg][]>()
  for (const entry of byKey) {
    const [key, agg] = entry
    const source = sourceFromKey(key)
    if (source === 'ozbargain' || source === 'camelcamelcamel') continue
    if (RETIRED_SOURCES.has(source)) continue
    if (!EVENT_EMITTING_SOURCES.has(source) && !isStillInLatestSourceBatch(key, agg)) continue
    // A card the reader can't act on is worse than a missing one — see
    // resolveUrl().
    if (resolveUrl(key, agg.latest) === '#') continue
    if (((agg.latest.age_hours as number) || 0) > NEW_SOURCE_MAX_AGE_HOURS) continue
    const region = dealRegion(source)
    const bucket = recencyBySection.get(region)
    if (bucket) bucket.push(entry)
    else recencyBySection.set(region, [entry])
  }

  // DealNews (and similar) can repost the same product under a new guid —
  // same title or same resolved URL, different deal key. Keep the freshest.
  function dedupeBucket(bucket: [string, Agg][]): [string, Agg][] {
    const byFreshness = [...bucket].sort(
      (a, b) => (b[1].latest.ts as string).localeCompare(a[1].latest.ts as string),
    )
    const seenTitles = new Set<string>()
    const seenUrls = new Set<string>()
    const deduped: [string, Agg][] = []
    for (const entry of byFreshness) {
      const [key, agg] = entry
      const titleKey = (agg.latest.title as string).trim().toLowerCase()
      const urlKey = resolveUrl(key, agg.latest)
      if (seenTitles.has(titleKey) || seenUrls.has(urlKey)) continue
      seenTitles.add(titleKey)
      seenUrls.add(urlKey)
      deduped.push(entry)
    }
    return deduped
  }

  const recencyCandidates: [string, Agg][] = []
  for (const bucket of recencyBySection.values()) {
    // Biggest discount first (a 57%-off flight beats an undiscounted forum
    // post); undated/undiscounted deals sort by recency instead of vanishing.
    const deduped = dedupeBucket(bucket)
    deduped.sort((a, b) => {
      const ma = CAPTURE_RANK[captureMode(sourceFromKey(a[0]), a[1].latest.title as string)]
      const mb = CAPTURE_RANK[captureMode(sourceFromKey(b[0]), b[1].latest.title as string)]
      if (ma !== mb) return mb - ma
      const da = (a[1].latest.discount_percent as number) ?? 0
      const db = (b[1].latest.discount_percent as number) ?? 0
      if (da !== db) return db - da
      return (b[1].latest.ts as string).localeCompare(a[1].latest.ts as string)
    })
    // Round-robin across the sources in this section rather than taking the
    // top N outright. A straight slice lets one source eat the whole section:
    // measured 2026-08-21, GLOBAL holds ~42 candidates of which AppSumo
    // contributes 33 at 40-75% off, so all 12 slots went to AppSumo and every
    // one of Vercel's free-AI-credit offers fell off — they carry no
    // discount_percent (the title says "for free", not "90% off"), so they
    // sort as 0 and lose to any discounted SaaS licence. Interleaving keeps
    // each source's own ordering while guaranteeing it a share of the section.
    // Round-robin runs WITHIN a capture tier, never across tiers. Measured live
    // 2026-08-21: interleaving by source alone handed smzdm's Apple Watch and
    // T-shirt listings every second slot in the CN section, pushing the v2ex
    // deals that are actually claimable from Australia down between them —
    // the capture rating was computed correctly and then discarded one step
    // later. Tier first (instant > unknown > shipped), source fairness inside
    // it, existing discount/recency ordering inside that.
    const capBase = recencyCandidates.length  // the cap is per section, not global
    const limit = capBase + NEW_SOURCE_SECTION_CAP
    for (const tier of [2, 1, 0]) {
      if (recencyCandidates.length >= limit) break
      const bySource = new Map<string, [string, Agg][]>()
      for (const entry of deduped) {
        const mode = captureMode(sourceFromKey(entry[0]), entry[1].latest.title as string)
        if (CAPTURE_RANK[mode] !== tier) continue
        const src = sourceFromKey(entry[0])
        const list = bySource.get(src)
        if (list) list.push(entry)
        else bySource.set(src, [entry])
      }
      const queues = [...bySource.values()]
      for (let i = 0; recencyCandidates.length < limit; i++) {
        const round = queues.filter((q) => q.length > i)
        if (!round.length) break
        for (const q of round) {
          if (recencyCandidates.length >= limit) break
          recencyCandidates.push(q[i])
        }
      }
    }
  }
  const recencyLive = await keepLive(toEntries(recencyCandidates))

  return [...live, ...recencyLive].map((e) => e.deal)
}

export function formatAge(ageHours: number): string {
  if (ageHours < 1) return `${Math.round(ageHours * 60)}m ago`
  if (ageHours < 24) return `${Math.round(ageHours)}h ago`
  return `${Math.round(ageHours / 24)}d ago`
}

// Mirrors SOURCE_LABELS in notify/render.py so the email and the website say
// the same thing about the same source.
const SOURCE_LABELS: Record<string, string> = {
  ozbargain: 'OzBargain',
  camelcamelcamel: 'CamelCamelCamel',
  dealnews: 'DealNews (US)',
  slickdeals: 'Slickdeals (US)',
  v2ex: 'V2EX (CN)',
  openrouter: 'OpenRouter',
  bank_rates: 'AU Bank Rates',
  iknowthepilot: 'Flight Deals (AU)',
  cn_llm_docs: 'CN AI Pricing',
  smzdm: '什么值得买',
  free_llm: 'Free LLM Tiers',
  appsumo: 'AppSumo (SaaS)',
  vercel: 'Vercel Offers',
  aff: 'Frequent Flyer (AU)',
  pointhacks: 'Point Hacks (AU)',
}
export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

export function currencySymbol(currency: string): string {
  if (currency === 'AUD') return '$'
  if (currency === 'CNY') return '¥'
  return 'US$'
}

// Frontend-only region grouping for the /deals page (Phase C2). Not a Deal
// field — filtering is already per-source config on the Python side, so
// there's nothing to add there.
export type DealRegion = 'AU' | 'NA' | 'CN' | 'GLOBAL'
const REGION_BY_SOURCE: Record<string, DealRegion> = {
  ozbargain: 'AU', camelcamelcamel: 'AU',
  bank_rates: 'AU', iknowthepilot: 'AU',
  aff: 'AU', pointhacks: 'AU',
  dealnews: 'NA', slickdeals: 'NA',
  v2ex: 'CN', cn_llm_docs: 'CN', smzdm: 'CN',
  openrouter: 'GLOBAL', appsumo: 'GLOBAL', vercel: 'GLOBAL', free_llm: 'GLOBAL',
}
export function dealRegion(source: string): DealRegion {
  return REGION_BY_SOURCE[source] ?? 'AU'
}

// Distinguishes deals the AU-based reader can actually receive (a digital
// licence key, a download, a data top-up) from ones that require a physical
// item to be shipped internationally to be useful to him. Source-level
// defaults come first for sources that are categorically one or the other;
// everything else falls to title inspection.
export type CaptureMode = 'instant' | 'shipped' | 'unknown'

// instant ranks above unknown ranks above shipped, used as the primary sort
// key ahead of discount/recency in getLiveDeals()'s per-section sort.
const CAPTURE_RANK: Record<CaptureMode, number> = { instant: 2, unknown: 1, shipped: 0 }

const CAPTURE_INSTANT_SOURCES = new Set([
  'appsumo', 'vercel', 'free_llm', 'openrouter', 'cn_llm_docs', 'bank_rates',
])
// Travel fares aren't parcels -- don't lump them in with 'shipped'.
const CAPTURE_UNKNOWN_SOURCES = new Set(['iknowthepilot', 'aff', 'pointhacks'])

// A physical-delivery marker must win over a digital-sounding word in the
// same title -- e.g. a NordVPN *subscription* bundle that also says "free
// shipping" ships a boxed key card, not a download. These are checked before
// CAPTURE_INSTANT_PATTERNS, never after.
const CAPTURE_SHIPPED_PATTERNS = [
  /free shipping/i,
  /\b\d+-pack\b/i,
  /\bsq\.?\s?ft\.?/i,
  // Chinese physical-goods listings are best caught by unit/packaging
  // markers, not by enumerating product/food words.
  /\d+(?:g|ml|片|罐|袋|盒)/,
  /\*\d+箱/,
  /礼盒/,
]

const CAPTURE_INSTANT_PATTERNS = [
  /digital delivery/i,
  /digital download/i,
  /\bdownload\b/i,
  /\bsubscription\b/i,
  /\blicense\b/i,
  /\bcredits?\b/i,
  /\bvpn\b/i,
  /\bantivirus\b/i,
  /\bsoftware\b/i,
  /会员/,
  /客户端/,
  /应用/,
  /终身版/,
  /送码/,
  /流量/,
  // Measured 2026-08-21 against a live v2ex harvest: without these, 4 of the 5
  // genuinely capturable CN deals fell through to the CJK fallback below and
  // were ranked to the bottom of their section -- the exact inversion this
  // rating exists to prevent. 额度/羊毛/免费领 carry the meaning that 会员 and
  // 流量 already did; they were simply missing.
  /额度/,
  /羊毛/,
  /免费领/,
  /免费领取/,
  /邀请码?/,
  /激活码|兑换码|序列号/,
  /\bcredits?\b/i,
  /\btokens?\b/i,
]

export function captureMode(source: string, title: string): CaptureMode {
  if (CAPTURE_INSTANT_SOURCES.has(source)) return 'instant'
  if (CAPTURE_UNKNOWN_SOURCES.has(source)) return 'unknown'
  if (CAPTURE_SHIPPED_PATTERNS.some((p) => p.test(title))) return 'shipped'
  if (CAPTURE_INSTANT_PATTERNS.some((p) => p.test(title))) return 'instant'
  // A CJK title that matched neither set is 'unknown', NOT 'shipped'.
  //
  // An earlier revision defaulted CJK to 'shipped' because the CN section was
  // then dominated by smzdm's physical-goods listings (mooncake gift boxes,
  // model-numbered earbuds) that carry no unit marker. smzdm was disabled the
  // same day -- see config/settings.yaml -- so that justification is gone,
  // while the cost was not: measured live, the fallback mislabelled "Kimi K3
  // 羊毛", "免费领取 100 刀 Fable 5 的使用额度" and "中银香港 boc + 10 元羊毛"
  // as physical goods and ranked them last. Guessing 'shipped' from script
  // alone buries the most capturable deals on the board; 'unknown' just
  // declines to rank them, which is the honest answer when nothing matched.
  return 'unknown'
}

// Verified 2026-08-21 against real titles pulled from the North America and
// China sections (see teammate brief) -- every one of these must classify as
// shown, checked by scripting captureMode() over this exact list:
//
// instant:
//   "Microsoft Windows 11 Pro Lifetime License for $10 + digital delivery"
//   "AdGuard Family Plan Lifetime Subscription for $11 + digital delivery"
//   "15-Months NordVPN Standard Internet Security (10 Devices/Digital Download) $25 & More"
//   "New Woot Customers: $14.99 | 1-Year NordVPN VPN & Cybersecurity Subscription (10-Device; Digital) at Woot!"
//   "Malwarebytes Standard Premium Security 3-Device 1-Year Antivirus Software for $13 + download"
//   "[跟一下] Chatgpt 客户端 1000 Credit 邀请，需要的来"
//   "[分享创造] [送码活动]： AI Smart Planner 应用（终身版）"
//   "[推广] 100MB-2GB 流量，免费出"
//   "分享一个酷狗音乐会员便宜的方法"
// shipped:
//   "Like-New Amazon eero mesh wifi router - Supports internet plans up to 550 Mbps, Coverage up to 1,500 sq. ft., 1-pack $32.99"
//   "Microsoft 365 Family 12-Month Subscription & NordVPN Basic 1-Year Bundle for $85 + free shipping"  <- physical marker wins over "Subscription"
//   "港荣 黄油牛角面包 420g*1箱"
//   "88VIP：桃李 提浆黑芝麻五仁豆沙馅 月饼"  <- no unit marker; caught by the CJK fallback
//   "乐事 薯片528g 104g*2罐+40g×8罐"
//   "塞那 Z60S AI骨传导 耳夹式蓝牙耳机"  <- "AI" is not treated as a digital marker (too generic); caught by the CJK fallback
