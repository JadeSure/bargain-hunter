// Build-time linkage between live deals (lib/deals.ts) and saving guides
// (lib/guides.ts). Deliberately dumb-but-explainable: lowercased word overlap
// with stopword filtering — no fuzzy matching, no ML — so every match can be
// traced back to specific words in the committed data.
//
// A deal matches a guide when any of these hold (tuned against the committed
// corpus in data/strategies/guides + data/observations, erring conservative —
// zero matches beat nonsense ones):
//
//   1. merchant hit + goal overlap — the deal's "@ Merchant" appears in the
//      guide text AND a distinctive goal word appears in the deal title
//      (e.g. "Apple AirPods 4 @ The Good Guys" → Buy Apple products guide).
//   2. merchant hit + ≥2 keyword overlaps — merchant appears in the guide
//      text and two significant title words also appear in the guide
//      (e.g. "Nintendo Switch 2 Console @ Target (Price Beat @ Officeworks)"
//      → gift-card + price-beat stack guide).
//   3. ≥3 keyword overlaps — strong text overlap alone, no merchant needed
//      (e.g. "5% off Amazon Gift Cards @ Bupa" → discounted gift card guide).
//
// A merchant hit alone is NOT enough: guides mention supermarkets like
// Woolworths as gift-card outlets, and without corroboration every grocery
// special would "match" a gift-card stacking guide.

import type { Guide } from './guides'
import type { LiveDeal } from './deals'

// Generic marketing/commerce filler that would otherwise produce noisy
// overlaps (every deal says "delivered", "eligible", "cashback cap", ...).
const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'from', 'this', 'that', 'your', 'you', 'are',
  'was', 'were', 'have', 'has', 'had', 'off', 'save', 'get', 'buy', 'new',
  'only', 'plus', 'free', 'via', 'use', 'using', 'used', 'spend', 'spending',
  'eligible', 'item', 'items', 'order', 'orders', 'purchase', 'purchases',
  'price', 'prices', 'deal', 'deals', 'offer', 'offers', 'delivered',
  'delivery', 'store', 'stores', 'instore', 'online', 'app', 'code', 'codes',
  'limited', 'stock', 'valid', 'terms', 'apply', 'applies', 'week', 'weeks',
  'day', 'days', 'month', 'months', 'monthly', 'annual', 'annually',
  'exclusive', 'required', 'activation', 'also', 'redeemable', 'capped',
  'per', 'min', 'max', 'more', 'including', 'includes', 'excl', 'excludes',
  'excluding', 'when', 'while', 'which', 'into', 'over', 'than', 'then',
  'each', 'all', 'any', 'some', 'can', 'will', 'not', 'about', 'after',
  'before', 'between', 'during', 'until', 'upon', 'within', 'without',
  'across', 'available', 'members', 'member', 'membership', 'customers',
  'customer', 'existing', 'account', 'accounts', 'everyday', 'market',
  'global', 'digital', 'physical', 'minimum', 'transaction', 'transactions',
  'bonus', 'credit', 'credits', 'promo', 'promotion', 'promotions',
  'promotional', 'selected', 'total', 'australia', 'australian', 'shoppers',
  'community', 'note', 'requires', 'first', 'full', 'life', 'rewards',
  'reward', 'daily', 'earn', 'work', 'works', 'best', 'products', 'product',
  'aim', 'pay', 'money', 'easy', 'open', 'just', 'single', 'value', 'pack',
  'targeted', 'uncapped', 'active', 'every', 'find', 'compare', 'cheapest',
  'launch', 'take', 'extra',
])

// Merchant names get a lower length bar (KFC, BWS, IGA), so also strip retail
// filler that appears inside merchant strings but identifies nothing
// ("Hunters Card Show", "Brand House Direct", "Bank of China").
const MERCHANT_EXTRA_STOPWORDS = new Set([
  'card', 'cards', 'gift', 'show', 'bank', 'shop', 'shopping', 'direct',
  'house', 'brand', 'group', 'warehouse', 'marketplace', 'world', 'com',
  'and', 'one',
])

// Technique-generic words excluded from the goal-token bonus: "cashback" in a
// goal must not let every cashback deal match on merchant + one word.
const TECHNIQUE_GENERIC = new Set([
  'cashback', 'gift', 'card', 'cards', 'giftcard', 'giftcards', 'discount',
  'discounted', 'savings', 'saving', 'deals', 'points', 'voucher', 'vouchers',
])

const MIN_KEYWORD_OVERLAP_WITH_MERCHANT = 2
const MIN_KEYWORD_OVERLAP_ALONE = 3
const MAX_GUIDES_PER_DEAL = 2
const MAX_DEALS_PER_GUIDE = 5

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 4 && !STOPWORDS.has(t) && !/^\d+$/.test(t))
}

function guideCorpus(guide: Guide): string {
  return [
    guide.goal,
    guide.summary,
    guide.category ?? '',
    guide.techniques.join(' ').replace(/_/g, ' '),
    ...guide.steps.map(
      (s) => `${s.action} ${s.detail ?? ''} ${(s.technique ?? '').replace(/_/g, ' ')}`,
    ),
  ].join(' ')
}

// Deal titles end "... @ Merchant Name (qualifier)" — take what follows the
// last "@" and drop any trailing parenthetical/bracketed qualifier.
function extractMerchant(title: string): string | null {
  const idx = title.lastIndexOf('@')
  if (idx === -1) return null
  const raw = title
    .slice(idx + 1)
    .replace(/[([].*$/, '')
    .trim()
  return raw || null
}

function merchantTokens(merchant: string): string[] {
  return merchant
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(
      (t) =>
        t.length >= 3 &&
        !STOPWORDS.has(t) &&
        !MERCHANT_EXTRA_STOPWORDS.has(t) &&
        !/^\d+$/.test(t),
    )
}

// Squash to bare alphanumerics so multi-part merchant names whose fragments
// are too short to tokenise ("JB Hi-Fi" → "jbhifi") can still be found as a
// phrase in the guide text.
function squash(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]/g, '')
}

type MatchReason = 'merchant' | 'keywords'

interface GuidePrep {
  guide: Guide
  text: string
  squashed: string
  tokens: Set<string>
  goalTokens: Set<string>
}

function prepareGuides(guides: Guide[]): GuidePrep[] {
  return guides.map((guide) => {
    const text = guideCorpus(guide)
    return {
      guide,
      text,
      squashed: squash(text),
      tokens: new Set(tokenize(text)),
      goalTokens: new Set(tokenize(guide.goal).filter((t) => !TECHNIQUE_GENERIC.has(t))),
    }
  })
}

function matchReason(
  dealTokens: Set<string>,
  mTokens: string[],
  mSquashed: string | null,
  prep: GuidePrep,
): MatchReason | null {
  let merchantHit = false
  for (const tok of mTokens) {
    if (new RegExp(`\\b${tok}\\b`, 'i').test(prep.text)) {
      merchantHit = true
      break
    }
  }
  // Fallback for names like "JB Hi-Fi" whose fragments are all too short to
  // tokenise: look for the squashed merchant phrase inside the guide text.
  if (!merchantHit && mSquashed && mSquashed.length >= 5 && prep.squashed.includes(mSquashed)) {
    merchantHit = true
  }
  let overlap = 0
  let goalOverlap = 0
  for (const t of dealTokens) {
    if (prep.tokens.has(t)) overlap++
    if (prep.goalTokens.has(t)) goalOverlap++
  }
  if (merchantHit && (goalOverlap >= 1 || overlap >= MIN_KEYWORD_OVERLAP_WITH_MERCHANT)) {
    return 'merchant'
  }
  if (overlap >= MIN_KEYWORD_OVERLAP_ALONE) return 'keywords'
  return null
}

export interface GuideDealMatches {
  /** deal key → up to MAX_GUIDES_PER_DEAL matching guides (merchant hits first) */
  dealToGuides: Map<string, Guide[]>
  /** guide id → up to MAX_DEALS_PER_GUIDE matching live deals (merchant hits first) */
  guideToDeals: Map<string, LiveDeal[]>
}

export function matchGuidesAndDeals(guides: Guide[], deals: LiveDeal[]): GuideDealMatches {
  const guidePrep = prepareGuides(guides)

  const dealToGuides = new Map<string, Guide[]>()
  const guideToDealsRaw = new Map<string, { deal: LiveDeal; reason: MatchReason }[]>()

  for (const deal of deals) {
    const merchant = extractMerchant(deal.title)
    const mTokens = merchant ? merchantTokens(merchant) : []
    const mSquashed = merchant ? squash(merchant) : null
    const mSet = new Set(mTokens)
    // Merchant tokens are excluded from keyword overlap so the merchant name
    // can't double-count as both signals.
    const dealTokens = new Set(tokenize(deal.title).filter((t) => !mSet.has(t)))

    const merchantMatches: Guide[] = []
    const keywordMatches: Guide[] = []

    for (const prep of guidePrep) {
      const reason = matchReason(dealTokens, mTokens, mSquashed, prep)
      if (!reason) continue
      if (reason === 'merchant') merchantMatches.push(prep.guide)
      else keywordMatches.push(prep.guide)

      const list = guideToDealsRaw.get(prep.guide.id) ?? []
      list.push({ deal, reason })
      guideToDealsRaw.set(prep.guide.id, list)
    }

    const ranked = [...merchantMatches, ...keywordMatches]
    if (ranked.length > 0) dealToGuides.set(deal.key, ranked.slice(0, MAX_GUIDES_PER_DEAL))
  }

  const guideToDeals = new Map<string, LiveDeal[]>()
  for (const [id, entries] of guideToDealsRaw) {
    // Deals arrive pre-sorted by hot tier/score (see getLiveDeals); a stable
    // partition keeps that ordering within each reason bucket.
    const merchantHits = entries.filter((e) => e.reason === 'merchant').map((e) => e.deal)
    const keywordHits = entries.filter((e) => e.reason === 'keywords').map((e) => e.deal)
    guideToDeals.set(id, [...merchantHits, ...keywordHits].slice(0, MAX_DEALS_PER_GUIDE))
  }

  return { dealToGuides, guideToDeals }
}

// getLiveDeals() does per-deal network expiry checks, so memoise the full
// matching result: /deals plus every guide page calls this during one build.
let cached: Promise<GuideDealMatches> | null = null

export async function getGuideDealMatches(): Promise<GuideDealMatches> {
  if (!cached) {
    cached = (async () => {
      const [{ getGuides }, { getLiveDeals }] = await Promise.all([
        import('./guides'),
        import('./deals'),
      ])
      const [guides, deals] = await Promise.all([getGuides(), getLiveDeals()])
      return matchGuidesAndDeals(guides, deals)
    })()
  }
  return cached
}
