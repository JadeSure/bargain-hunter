// Reads gift-card / cashback deals from OzBargain's public tag feeds at build
// time (Next.js static generation), mirroring the build-time fetch pattern in
// lib/deals.ts (isOzbargainInactive) and the edge-safe []-on-failure contract of
// lib/guides.ts. Kept out of the email hot flow — this powers the /gift-cards
// board only. Refreshed on each Pages rebuild (~every 30 min via CI).

export interface GiftCardDeal {
  id: string
  title: string
  url: string
  merchant: string | null
  valueHint: string | null
  votesPos: number
  commentCount: number
  expiry: string | null
  image: string | null
  ts: string
}

const GIFT_CARD_FEEDS = [
  'https://www.ozbargain.com.au/tag/gift-card/feed',
  'https://www.ozbargain.com.au/tag/cashback/feed',
]
const OZB_USER_AGENT =
  'bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)'

function decodeEntities(s: string): string {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;/g, "'")
    .replace(/&#x27;/gi, "'")
    .replace(/&apos;/g, "'")
    .trim()
}

function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`${name}="([^"]*)"`))
  return m ? decodeEntities(m[1]) : null
}

function hostOf(url: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).hostname.replace(/^www\./, '') || null
  } catch {
    return null
  }
}

// Pull a short, human "what's the saving" chip out of the deal title.
const VALUE_PATTERNS: RegExp[] = [
  /\b\d+(?:\.\d+)?%\s*(?:off|cashback|discount)\b/i,
  /\b\d+x\s*(?:bonus\s*)?(?:edr|flybuys|reward|krisflyer|velocity)?\s*(?:points|pts|miles)\b/i,
  /\bbonus\s*[\d,]+\s*(?:points|pts)\b/i,
  /\b\$\d+(?:\.\d+)?\s*(?:egift|gift|visa|credit|back|off)\b/i,
]

function valueHint(title: string): string | null {
  for (const re of VALUE_PATTERNS) {
    const m = title.match(re)
    if (m) return m[0].replace(/\s+/g, ' ').trim()
  }
  return null
}

function parseFeed(xml: string): GiftCardDeal[] {
  const out: GiftCardDeal[] = []
  const items = xml.match(/<item>[\s\S]*?<\/item>/g) ?? []
  for (const item of items) {
    const titleMsg = item.match(/<ozb:title-msg\s+type="([^"]+)"/)
    const status = titleMsg?.[1]?.toLowerCase()
    if (status === 'expired' || status === 'upcoming') continue // not currently claimable

    const link = decodeEntities(item.match(/<link>([\s\S]*?)<\/link>/)?.[1] ?? '')
    const title = decodeEntities(item.match(/<title>([\s\S]*?)<\/title>/)?.[1] ?? '')
    if (!link || !title) continue
    const id = link.match(/\/node\/(\d+)/)?.[1] ?? link

    const metaTag = item.match(/<ozb:meta\b[^>]*\/>/)?.[0] ?? ''
    const expiry = attr(metaTag, 'expiry')
    if (expiry) {
      const exp = Date.parse(expiry)
      if (!Number.isNaN(exp) && exp < Date.now()) continue // expiry already passed
    }

    out.push({
      id,
      title,
      url: link,
      merchant: hostOf(attr(metaTag, 'url')),
      valueHint: valueHint(title),
      votesPos: Number(attr(metaTag, 'votes-pos') ?? '0') || 0,
      commentCount: Number(attr(metaTag, 'comment-count') ?? '0') || 0,
      expiry,
      image: attr(metaTag, 'image'),
      ts: decodeEntities(item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1] ?? ''),
    })
  }
  return out
}

export async function getGiftCardDeals(): Promise<GiftCardDeal[]> {
  const results = await Promise.all(
    GIFT_CARD_FEEDS.map(async (feed) => {
      try {
        const res = await fetch(feed, {
          signal: AbortSignal.timeout(10000),
          headers: { 'User-Agent': OZB_USER_AGENT },
        })
        if (!res.ok) return []
        return parseFeed(await res.text())
      } catch {
        return [] // fail open — a feed hiccup shouldn't blank the board
      }
    }),
  )

  // Dedup by node id (a deal can carry both gift-card and cashback tags).
  const byId = new Map<string, GiftCardDeal>()
  for (const deal of results.flat()) {
    if (!byId.has(deal.id)) byId.set(deal.id, deal)
  }

  // Most-upvoted first — the community's strongest signal for gift-card value.
  return [...byId.values()].sort((a, b) => b.votesPos - a.votesPos)
}

export function giftCardExpiryLabel(expiry: string | null): string | null {
  if (!expiry) return null
  const ms = Date.parse(expiry)
  if (Number.isNaN(ms)) return null
  const days = Math.ceil((ms - Date.now()) / 86_400_000)
  if (days <= 0) return 'ending today'
  if (days === 1) return 'ends tomorrow'
  if (days <= 14) return `ends in ${days}d`
  return `until ${new Date(ms).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`
}
