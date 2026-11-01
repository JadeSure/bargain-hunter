'use client'

import { useState } from 'react'
import { money } from '@/lib/bf2026-derive'
import { unpackUrl } from './shared'

// Rows are built only once the <details> is opened, so the collapsed page carries the data once
// (as props) instead of also carrying hundreds of rendered cells.

export type HistoryRow = [date: string, event: string, price: number, conditions: string, retailer: string, source: string]

export function HistoryDetails({ summary, rows, more }: { summary: string; rows: HistoryRow[]; more: number }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="mt-4 text-sm" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="bf-toggle">{summary}</summary>
      {open && (
        <div className="mt-3 overflow-x-auto rounded-lg bg-zinc-950/60 p-2">
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
