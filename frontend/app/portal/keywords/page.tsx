'use client'

import { useState, useRef, KeyboardEvent } from 'react'
import { useUser } from '../context'
import {
  parseWatchKeyword,
  serializeWatchKeyword,
  isValidMaxPrice,
  isValidExpiry,
  type StructuredKeyword,
} from '@/lib/watchKeyword'

let nextId = 0
function newId(): string {
  nextId += 1
  return `kw-${nextId}`
}

// A row is either structured (phrase/maxPrice/expiry, parsed from — and
// serialised back to — the pipeline's "PHRASE [<=PRICE] [@EXPIRY]" syntax) or
// raw (the stored string didn't cleanly parse, so we show it as free text
// rather than risk mangling it).
type WatchRow =
  | { id: string; mode: 'structured'; value: StructuredKeyword }
  | { id: string; mode: 'raw'; raw: string }

function toRows(keywords: string[]): WatchRow[] {
  return keywords.map((raw) => {
    const parsed = parseWatchKeyword(raw)
    return parsed
      ? { id: newId(), mode: 'structured', value: parsed }
      : { id: newId(), mode: 'raw', raw }
  })
}

function rowToString(row: WatchRow): string {
  return row.mode === 'raw' ? row.raw : serializeWatchKeyword(row.value)
}

function WatchKeywordPanel({ keywords, onSave }: { keywords: string[]; onSave: (keywords: string[]) => Promise<void> }) {
  const [rows, setRows] = useState<WatchRow[]>(() => toRows(keywords))
  const [phrase, setPhrase] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [expiry, setExpiry] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const phraseRef = useRef<HTMLInputElement>(null)

  const priceValid = isValidMaxPrice(maxPrice)
  const expiryValid = isValidExpiry(expiry)
  const canAdd = phrase.trim().length > 0 && priceValid && expiryValid

  function markDirty() { setDirty(true); setSaved(false) }

  function addRow() {
    if (!canAdd) return
    setRows([
      ...rows,
      { id: newId(), mode: 'structured', value: { phrase: phrase.trim(), maxPrice: maxPrice.trim(), expiry: expiry.trim() } },
    ])
    setPhrase('')
    setMaxPrice('')
    setExpiry('')
    markDirty()
    phraseRef.current?.focus()
  }

  function removeRow(id: string) {
    setRows(rows.filter((r) => r.id !== id))
    markDirty()
  }

  function updateRow(id: string, patch: Partial<StructuredKeyword>) {
    setRows(
      rows.map((r) => (r.id === id && r.mode === 'structured' ? { ...r, value: { ...r.value, ...patch } } : r))
    )
    markDirty()
  }

  function updateRaw(id: string, raw: string) {
    setRows(rows.map((r) => (r.id === id ? { ...r, raw } : r)))
    markDirty()
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') { e.preventDefault(); addRow() }
  }

  const rowsValid = rows.every((r) => r.mode === 'raw' || (isValidMaxPrice(r.value.maxPrice) && isValidExpiry(r.value.expiry)))

  async function handleSave() {
    if (!rowsValid) return
    setSaving(true)
    try {
      await onSave(rows.map(rowToString).filter(Boolean))
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="kw-panel">
      <div className="kw-panel-title">Watch keywords</div>
      <div className="kw-panel-hint">
        Get alerted when a deal matches. Optionally cap it to a max price (e.g. Dyson ≤$600) or an
        expiry time — after which the keyword stops firing.
      </div>

      <div className="kw-rows">
        {rows.map((row) => (
          <div className="kw-row" key={row.id}>
            {row.mode === 'raw' ? (
              <>
                <input
                  className="kw-row-input kw-row-raw"
                  type="text"
                  value={row.raw}
                  onChange={(e) => updateRaw(row.id, e.target.value)}
                  aria-label="Raw keyword (couldn't be parsed into phrase / price / expiry)"
                />
                <span className="kw-row-raw-tag" title="Couldn't parse this into phrase / price / expiry — editing as raw text">raw</span>
              </>
            ) : (
              <>
                <input
                  className="kw-row-input kw-row-phrase"
                  type="text"
                  value={row.value.phrase}
                  onChange={(e) => updateRow(row.id, { phrase: e.target.value })}
                  aria-label="Keyword phrase"
                />
                <span className="kw-row-op">≤$</span>
                <input
                  className={`kw-row-input kw-row-price ${!isValidMaxPrice(row.value.maxPrice) ? 'kw-row-input-error' : ''}`}
                  type="text"
                  inputMode="decimal"
                  placeholder="any"
                  value={row.value.maxPrice}
                  onChange={(e) => updateRow(row.id, { maxPrice: e.target.value })}
                  aria-label="Max price"
                />
                <span className="kw-row-op">@</span>
                <input
                  className={`kw-row-input kw-row-expiry ${!isValidExpiry(row.value.expiry) ? 'kw-row-input-error' : ''}`}
                  type="text"
                  placeholder="HH:MM or never"
                  value={row.value.expiry}
                  onChange={(e) => updateRow(row.id, { expiry: e.target.value })}
                  aria-label="Expiry (HH:MM today, or YYYY-MM-DDTHH:MM)"
                />
              </>
            )}
            <button className="kw-pill-remove kw-row-remove" onClick={() => removeRow(row.id)} aria-label="Remove keyword">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <div className="kw-add-row kw-add-row-structured">
        <input
          ref={phraseRef}
          className="kw-row-input kw-row-phrase"
          type="text"
          placeholder="Add a keyword…"
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <span className="kw-row-op">≤$</span>
        <input
          className={`kw-row-input kw-row-price ${!priceValid ? 'kw-row-input-error' : ''}`}
          type="text"
          inputMode="decimal"
          placeholder="any"
          value={maxPrice}
          onChange={(e) => setMaxPrice(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <span className="kw-row-op">@</span>
        <input
          className={`kw-row-input kw-row-expiry ${!expiryValid ? 'kw-row-input-error' : ''}`}
          type="text"
          placeholder="HH:MM or never"
          value={expiry}
          onChange={(e) => setExpiry(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="btn-kw-add" onClick={addRow} disabled={!canAdd} type="button">Add</button>
      </div>
      {(!priceValid || !expiryValid) && (
        <div className="kw-row-error-hint">
          {!priceValid && <span>Max price must be a positive number. </span>}
          {!expiryValid && <span>Expiry must be HH:MM or YYYY-MM-DDTHH:MM.</span>}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '16px' }}>
        <span style={{ fontSize: '12px', color: 'rgba(232,233,236,0.35)' }}>
          {rows.length} keyword{rows.length !== 1 ? 's' : ''}
        </span>
        {dirty && (
          <button className="btn-save" onClick={handleSave} disabled={saving || !rowsValid}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}
        {saved && !dirty && <span className="save-status">Saved ✓</span>}
      </div>
    </div>
  )
}

function BlockKeywordPanel({ keywords, onSave }: { keywords: string[]; onSave: (keywords: string[]) => Promise<void> }) {
  const [items, setItems] = useState<string[]>(keywords)
  const [input, setInput] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function add() {
    const val = input.trim()
    if (!val || items.includes(val)) { setInput(''); return }
    setItems([...items, val])
    setInput('')
    setDirty(true)
    setSaved(false)
  }

  function remove(kw: string) {
    setItems(items.filter((k) => k !== kw))
    setDirty(true)
    setSaved(false)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
    if (e.key === 'Backspace' && !input && items.length > 0) remove(items[items.length - 1])
  }

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(items)
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="kw-panel">
      <div className="kw-panel-title">Block keywords</div>
      <div className="kw-panel-hint">Suppress deals that contain any of these terms.</div>

      <div className="kw-pills">
        {items.map((kw) => (
          <span key={kw} className="kw-pill kw-pill-neutral">
            {kw}
            <button
              className="kw-pill-remove"
              onClick={() => remove(kw)}
              aria-label={`Remove ${kw}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </span>
        ))}
      </div>

      <div className="kw-add-row">
        <input
          ref={inputRef}
          className="kw-add-input"
          type="text"
          placeholder="Add a keyword…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="btn-kw-add" onClick={add} type="button">Add</button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '16px' }}>
        <span style={{ fontSize: '12px', color: 'rgba(232,233,236,0.35)' }}>
          {items.length} keyword{items.length !== 1 ? 's' : ''}
        </span>
        {dirty && (
          <button className="btn-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}
        {saved && !dirty && <span className="save-status">Saved ✓</span>}
      </div>
    </div>
  )
}

export default function KeywordsPage() {
  const { user, saveUpdate } = useUser()

  return (
    <div className="portal-page">
      <h1 className="portal-page-title">Keywords</h1>
      <p className="portal-page-sub">Control which deals you get alerted about.</p>

      <div className="keywords-grid">
        <WatchKeywordPanel
          keywords={user.watchKeywords}
          onSave={(watchKeywords) => saveUpdate({ watchKeywords })}
        />
        <BlockKeywordPanel
          keywords={user.blockKeywords}
          onSave={(blockKeywords) => saveUpdate({ blockKeywords })}
        />
      </div>
    </div>
  )
}
