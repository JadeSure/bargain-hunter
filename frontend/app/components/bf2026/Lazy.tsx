'use client'

import { useState } from 'react'
import { money } from '@/lib/bf2026-derive'
import { TABLE_CLASS, unpackUrl } from './shared'

// Both components below only build their rows once the <details> is opened, so the collapsed
// page carries the data once (as props) instead of also carrying hundreds of rendered cells.

export type HistoryRow = [date: string, event: string, price: number, conditions: string, retailer: string, source: string]

export function HistoryDetails({ summary, rows, more }: { summary: string; rows: HistoryRow[]; more: number }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="mt-3 text-sm" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-zinc-300">{summary}</summary>
      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[420px] text-xs text-zinc-300 [&_td]:whitespace-nowrap [&_td]:py-1 [&_td]:pr-3">
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{r[0]}</td>
                  <td>{r[1]}</td>
                  <td>{money(r[2])}</td>
                  <td>{r[3] || '—'}</td>
                  <td><a href={unpackUrl(r[5])} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{r[4] || '来源'}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
          {more > 0 && <div className="mt-1 text-zinc-400">另有 {more} 条较早的未列出</div>}
        </div>
      )}
    </details>
  )
}

export type PromoRow = [retailer: string, kind: string, value: string, start: string, end: string, scope: string, conditions: string, source: string]

export function PromoYear({ year, rows }: { year: number; rows: PromoRow[] }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="mb-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-sm font-medium text-zinc-100">{year} 年（{rows.length} 条）</summary>
      {open && (
        <div className="mt-2 overflow-x-auto rounded-lg border border-zinc-800">
          <table className={TABLE_CLASS} style={{ minWidth: 760 }}>
            <thead><tr><th>类型</th><th>力度</th><th>起止</th><th>范围</th><th>条件</th><th>来源</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <PromoLine key={i} r={r} first={i === 0 || rows[i - 1][0] !== r[0]} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  )
}

function PromoLine({ r, first }: { r: PromoRow; first: boolean }) {
  return (
    <>
      {first && (
        <tr>
          <td colSpan={6} className="bg-zinc-900 font-medium text-zinc-100">{r[0]}</td>
        </tr>
      )}
      <tr>
        <td className="whitespace-nowrap">{r[1]}</td>
        <td>{r[2]}</td>
        <td className="whitespace-nowrap">{r[3] || '?'} – {r[4] || '?'}</td>
        <td className="max-w-[16rem] break-words">{r[5]}</td>
        <td>{r[6] || '—'}</td>
        <td><a href={unpackUrl(r[7])} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">链接</a></td>
      </tr>
    </>
  )
}
