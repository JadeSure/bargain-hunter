// Structured parsing/serialisation for the pipeline's watch-keyword syntax:
//   PHRASE [<=PRICE] [@HH:MM | @YYYY-MM-DDTHH:MM]
// Mirrors src/bargain_hunter/matching.py `_parse_keyword` — keep in sync.

export interface StructuredKeyword {
  phrase: string
  maxPrice: string // '' = no ceiling, otherwise a plain (unformatted) number string
  expiry: string // '' = no expiry, otherwise "HH:MM" or "YYYY-MM-DDTHH:MM"
}

const PRICE_TOKEN = /^[\d,]+(?:\.\d+)?$/
const TIME_TOKEN = /^\d{2}:\d{2}(?::\d{2})?$/
const DATETIME_TOKEN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/

// Same shape as the Python regex, but we additionally sanity-check that any
// "<=" / "@" present in the source was actually consumed as a price/expiry
// token — otherwise we'd silently fold a malformed marker into the phrase.
const KW_RE =
  /^(.*?)(?:\s*<=\s*([\d,]+(?:\.\d+)?))?(?:\s*@(\d{2}:\d{2}(?::\d{2})?|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?))?\s*$/

/** Parse a raw stored keyword string into structured fields, or null if it
 * doesn't cleanly conform to the pipeline syntax (caller should fall back to
 * showing the raw text so nothing is silently mangled). */
export function parseWatchKeyword(raw: string): StructuredKeyword | null {
  const trimmed = raw.trim()
  if (!trimmed) return null

  const m = KW_RE.exec(trimmed)
  if (!m) return null

  const [, phraseRaw, priceRaw, expiryRaw] = m
  const phrase = (phraseRaw ?? '').trim()
  if (!phrase) return null

  // If the source contains a "<=" or "@" marker that wasn't captured as a
  // valid price/expiry token, treat the whole thing as unparseable.
  if (trimmed.includes('<=') && priceRaw === undefined) return null
  if (trimmed.includes('@') && expiryRaw === undefined) return null

  return {
    phrase,
    maxPrice: priceRaw ? priceRaw.replace(/,/g, '') : '',
    expiry: expiryRaw ?? '',
  }
}

/** Serialise structured fields back into the pipeline's exact keyword syntax. */
export function serializeWatchKeyword(kw: StructuredKeyword): string {
  let out = kw.phrase.trim()
  const price = kw.maxPrice.trim()
  const expiry = kw.expiry.trim()
  if (price) out += ` <=${price}`
  if (expiry) out += ` @${expiry}`
  return out
}

export function isValidMaxPrice(value: string): boolean {
  if (!value.trim()) return true
  const n = Number(value)
  return Number.isFinite(n) && n > 0
}

export function isValidExpiry(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return true
  return TIME_TOKEN.test(trimmed) || DATETIME_TOKEN.test(trimmed)
}

export { PRICE_TOKEN }
