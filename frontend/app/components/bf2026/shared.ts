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

// History rows go to the browser as props, so the two big sites are sent as short ids and rebuilt there.
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

export const clip = (s: string, n = 70) => (s.length > n ? s.slice(0, n - 1) + '…' : s)
