'use client'

// Client component only for size: the card text is sent once as props instead of twice (HTML + server payload).

import Bars from './Bars'
import { HistoryDetails } from './Lazy'
import type { HistoryRow } from './Lazy'

export interface WatchCard {
  key: string
  item: string
  who: string
  why: string
  confidence: string
  range: string
  earliest: string | null
  // mini bar: [nowLabel, nowPrice, nowText, forecastPrice, forecastText]
  bar: [string, number, string, number, string] | null
  kw: string
  broad: boolean
  // [item, date, file, verifyLabel, source]
  basis: [string, string, string, string, string] | null
  // [text, link] — per-season BF minimums
  seasons: { text: string; link: string } | null
  summary: string
  rows: HistoryRow[]
  more: number
}

const link = (href: string, text: string) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{text}</a>
)

export default function Cards({ groups }: { groups: { title: string; cards: WatchCard[] }[] }) {
  return (
    <>
      {groups.map((g) => (
        <div key={g.title} className="mb-8">
          <h3 className="mb-3 font-medium text-zinc-100">{g.title}（{g.cards.length}）</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {g.cards.map((c) => (
              <div key={c.key} id={c.key} className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium text-zinc-50">{c.item}</div>
                  <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">信心 {c.confidence}</span>
                </div>
                <div className="text-sm text-zinc-400">送谁：{c.who}</div>
                <div className="mt-2 text-sm">
                  预计黑五价：<span className="font-semibold text-sky-300">{c.range || '没有往年黑五价'}</span>
                </div>
                {c.earliest && <div className="text-sm text-zinc-400">往年最早 {c.earliest} 出现</div>}
                {c.bar && (
                  <div className="mt-3">
                    <Bars
                      thin
                      rows={[
                        { label: c.bar[0], value: c.bar[1], text: c.bar[2] },
                        { label: '预计黑五', value: c.bar[3], text: c.bar[4], accent: true },
                      ]}
                    />
                  </div>
                )}
                <div className="mt-3 text-sm">
                  提醒 <code className="select-all break-all rounded bg-zinc-800 px-1.5 py-0.5">{c.kw}</code>
                </div>
                {c.basis && (
                  <div className="mt-1 break-words text-xs text-zinc-400">
                    提醒价依据：{link(c.basis[4], c.basis[0])} · {c.basis[1]} · {c.basis[2]}（{c.basis[3]}）
                    {c.broad && ' · 这个关键词涵盖多种商品，只采用人工核对的点'}
                  </div>
                )}
                <div className="mt-2 break-words text-sm text-zinc-400">
                  依据：{c.seasons && <>{link(c.seasons.link, c.seasons.text)}。</>}{c.why}
                </div>
                <HistoryDetails summary={c.summary} rows={c.rows} more={c.more} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  )
}
