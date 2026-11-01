'use client'

// Client component only for size: the card text is sent once as props instead of twice (HTML + server payload).

import Bars from './Bars'
import Thumb from './Thumb'
import { HistoryDetails } from './Lazy'
import type { HistoryRow } from './Lazy'
import { pillFor } from './shared'

export interface WatchCard {
  key: string
  item: string
  category: string
  image?: string
  advice: string
  verdict: string
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
  <a href={href} target="_blank" rel="noopener noreferrer" className="bf-link">{text}</a>
)

const DOTS: Record<string, string> = { 高: '●●●', 中: '●●○', 低: '●○○' }

export default function Cards({ groups }: { groups: { verdict: string; title: string; cards: WatchCard[] }[] }) {
  return (
    <>
      {groups.map((g) => (
        <div key={g.title} className="mb-8 last:mb-0">
          <h3 className={`bf-pill mb-4 px-3 py-1 text-sm ${pillFor(g.verdict)}`}>{g.title} · {g.cards.length}</h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {g.cards.map((c) => (
              <div key={c.key} id={c.key} className="bf-card p-4 sm:p-5">
                <div className="flex gap-3">
                  <Thumb image={c.image} name={c.item} category={c.category} size={72} />
                  <div className="min-w-0 flex-1">
                    <div className="bf-name">{c.item}</div>
                    <div className="bf-badges">
                      <span className={`${pillFor(c.verdict)}`}>{c.advice}</span>
                      <span className="bf-m" aria-label={`信心 ${c.confidence}`}>
                        信心 <span aria-hidden className="bf-dots">{DOTS[c.confidence]}</span> {c.confidence}
                      </span>
                    </div>
                    <div className="bf-sub">送谁：{c.who}</div>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="bf-m">预计黑五价</div>
                  <div className="bf-price">{c.range || '没有往年黑五价'}</div>
                  {c.earliest && <div className="text-sm text-zinc-400">往年最早 {c.earliest} 出现</div>}
                </div>
                {c.bar && (
                  <div className="mt-4">
                    <Bars
                      thin
                      rows={[
                        { label: c.bar[0], value: c.bar[1], text: c.bar[2] },
                        { label: '预计黑五', value: c.bar[3], text: c.bar[4], accent: true },
                      ]}
                    />
                  </div>
                )}
                <div className="bf-kwrow">
                  <span aria-hidden>🔔</span>提醒
                  <code className="bf-kw">{c.kw}</code>
                </div>
                {c.basis && (
                  <div className="bf-note">
                    提醒价依据：{link(c.basis[4], c.basis[0])} · {c.basis[1]} · {c.basis[2]}（{c.basis[3]}）
                    {c.broad && ' · 这个关键词涵盖多种商品，只采用人工核对的点'}
                  </div>
                )}
                <div className="bf-note">
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
