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

// One colour per meaning, used by pills, group labels and gift lists. Classes are written out in full so Tailwind finds them.
export const ADVICE: { verdict: string; title: string; short: string; pill: string }[] = [
  { verdict: '黑五入手', title: '等黑五买', short: '等黑五买', pill: 'bf-sky' },
  { verdict: '现在可买', title: '现在就可以买', short: '现在可买', pill: 'bf-emerald' },
  { verdict: '不用等黑五', title: '不用等黑五（别的时候更便宜）', short: '不用等黑五', pill: 'bf-amber' },
  { verdict: '小心虚标', title: '小心假折扣', short: '小心假折扣', pill: 'bf-rose' },
]
export const OTHER_PILL = 'bf-zinc'
export const pillFor = (verdict: string) => ADVICE.find((a) => a.verdict === verdict)?.pill ?? OTHER_PILL
