'use client'

import { HistoryDetails } from './Lazy'
import type { HistoryRow } from './Lazy'
import { unpackUrl } from './shared'

export interface WatchCard {
  key: string
  verdict: string
  item: string
  who: string
  why: string
  kw: string
  broad: boolean
  range: string
  // [priceText, date, conditions, source]
  seen: [string, string, string, string] | null
  target: string
  // [item, date, file, verifyLabel, source]
  basis: [string, string, string, string, string] | null
  summary: string
  rows: HistoryRow[]
  more: number
}

const link = (href: string, text: string) => (
  <a href={unpackUrl(href)} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{text}</a>
)

// Client component: the card text is sent once as props instead of twice (HTML + server payload).
export default function Cards({ verdicts, cards }: { verdicts: string[]; cards: WatchCard[] }) {
  return (
    <>
      {verdicts.map((v) => {
        const rows = cards.filter((c) => c.verdict === v)
        if (!rows.length) return null
        return (
          <div key={v} className="mb-6">
            <div className="mb-2 text-sm font-medium text-zinc-100">{v}（{rows.length}）</div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {rows.map((c) => (
                <div key={c.key} className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                  <div className="font-medium text-zinc-50">{c.item}</div>
                  <div className="text-sm text-zinc-400">{c.who}</div>
                  <div className="mt-2 break-words text-sm">
                    往年黑五 {c.range || '—'} · 今年已见{' '}
                    {c.seen ? link(c.seen[3], `${c.seen[0]}（${c.seen[1]}${c.seen[2] ? `，${c.seen[2]}` : ''}）`) : '—'} · 提醒价 {c.target}
                  </div>
                  {c.basis && (
                    <div className="mt-1 break-words text-xs text-zinc-400">
                      提醒价依据：{link(c.basis[4], c.basis[0])} · {c.basis[1]} · {c.basis[2]}（{c.basis[3]}）
                      {c.broad && ' · 这个关键词涵盖多种商品，只采用人工核对的点'}
                    </div>
                  )}
                  <div className="mt-2 break-words text-sm text-zinc-400">{c.why}</div>
                  <code className="mt-3 inline-block select-all break-all rounded bg-zinc-800 px-1.5 py-0.5 text-sm">{c.kw}</code>
                  <HistoryDetails summary={c.summary} rows={c.rows} more={c.more} />
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}
