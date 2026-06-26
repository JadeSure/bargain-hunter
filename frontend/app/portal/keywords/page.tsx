'use client'

import { useState, useRef, KeyboardEvent } from 'react'
import { useUser } from '../context'

function KeywordPanel({
  title,
  description,
  keywords,
  pillClass,
  onSave,
}: {
  title: string
  description: string
  keywords: string[]
  pillClass: 'kw-pill-teal' | 'kw-pill-neutral'
  onSave: (keywords: string[]) => Promise<void>
}) {
  const [items, setItems] = useState<string[]>(keywords)
  const [input, setInput] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function add() {
    const val = input.trim().toLowerCase()
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
      <div className="kw-panel-title">{title}</div>
      <div className="kw-panel-hint">{description}</div>

      <div className="kw-pills">
        {items.map((kw) => (
          <span key={kw} className={`kw-pill ${pillClass}`}>
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
        <KeywordPanel
          title="Watch keywords"
          description="Get alerted when a deal title contains any of these terms."
          keywords={user.watchKeywords}
          pillClass="kw-pill-teal"
          onSave={(watchKeywords) => saveUpdate({ watchKeywords })}
        />
        <KeywordPanel
          title="Block keywords"
          description="Suppress deals that contain any of these terms."
          keywords={user.blockKeywords}
          pillClass="kw-pill-neutral"
          onSave={(blockKeywords) => saveUpdate({ blockKeywords })}
        />
      </div>
    </div>
  )
}
