// Constants shared by the server page and the client explorer (no 'use client' here, so both can import).

export const CAT_COLOR: Record<string, string> = {
  数码电子: '#38bdf8',
  家电厨房: '#fbbf24',
  美妆个护: '#f472b6',
  户外运动: '#34d399',
  保健食品: '#a78bfa',
  礼品: '#fb923c',
  其他: '#a1a1aa',
}

// How much each source file was hand-checked. Update when the data owner reports a new audit.
export function verifyLabel(file: string): string {
  if (file === 'curated') return '人工核对'
  if (file === 'ozbargain' || file === 'ozbargain-boxing-day') return '抽查 508/508 吻合'
  if (file === 'dealmoon') return '未抽查（网站拦截脚本）'
  return '未抽查'
}

// Table cell styles live on the <table> so each of the hundreds of cells stays small in the HTML.
export const TABLE_CLASS =
  'w-full text-sm text-zinc-200 [&_th]:whitespace-nowrap [&_th]:border-b [&_th]:border-zinc-700 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-medium [&_th]:text-zinc-300 [&_td]:border-b [&_td]:border-zinc-800 [&_td]:px-3 [&_td]:py-2 [&_td]:align-top'

// Source URLs dominate the payload, so the two big sites are sent as short ids and rebuilt in the browser.
const PREFIXES: [string, string][] = [
  ['o:', 'https://www.ozbargain.com.au/node/'],
  ['d:', 'https://www.dealmoon.com.au/product/'],
]
export function packUrl(url: string): string {
  for (const [short, long] of PREFIXES) if (url.startsWith(long)) return short + url.slice(long.length)
  return url
}
export function unpackUrl(packed: string): string {
  for (const [short, long] of PREFIXES) if (packed.startsWith(short)) return long + packed.slice(short.length)
  return packed
}

// ── Compact wire format for the client explorer (tuples + indexes instead of objects) ──
// Every row here would otherwise repeat its key names and category/file strings; with thousands of
// bytes per row that is what blows the HTML budget.
export const clip = (s: string, n = 70) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

export type SideTuple = [item: string, price: number, date: string, event: string, retailer: string, file: number, votes: number, source: string, note: string]
export type PairTuple = [key: string, category: number, year: number, comparable: 0 | 1, a: SideTuple, b: SideTuple]
export type DealTuple = [item: string, retailer: string, source: string, file: number, category: number, year: number, event: 0 | 1, price: number, was: number, pct: number, votes: number]
export type ExcludedTuple = [item: string, price: number, was: number, pct: number, reason: string, source: string]
