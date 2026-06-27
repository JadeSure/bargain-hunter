'use client'

import { useState } from 'react'
import { useUser } from '../context'

const CHANNEL_OPTIONS = [
  { id: 'telegram', label: 'Telegram' },
  { id: 'email', label: 'Email' },
]

const CATEGORY_OPTIONS = [
  { id: 'electronics', label: 'Electronics' },
  { id: 'home', label: 'Home & Garden' },
  { id: 'fashion', label: 'Fashion' },
  { id: 'sports', label: 'Sports & Outdoors' },
  { id: 'toys', label: 'Toys & Games' },
  { id: 'beauty', label: 'Beauty & Health' },
  { id: 'food', label: 'Food & Grocery' },
  { id: 'travel', label: 'Travel' },
]

const HOT_LEVEL_OPTIONS = [
  { id: '', label: 'Good & up — all hot deals' },
  { id: 'great', label: 'Great & up — strong deals only' },
  { id: 'top', label: 'Top only — best of the best' },
]

export default function SettingsPage() {
  const { user, saveUpdate } = useUser()

  const [subscribeHot, setSubscribeHot] = useState(user.subscribeHot)
  const [minDiscount, setMinDiscount] = useState<string>(
    user.minDiscountPercent != null ? String(user.minDiscountPercent) : ''
  )
  const [maxAlerts, setMaxAlerts] = useState<string>(String(user.maxAlertsPerDay))
  const [maxWatchAlerts, setMaxWatchAlerts] = useState<string>(String(user.maxWatchAlertsPerDay))
  const [channels, setChannels] = useState<string[]>(user.channels)
  const [categories, setCategories] = useState<string[]>(user.categories)
  const [hotLevel, setHotLevel] = useState<string>(user.hotLevel ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)

  function markDirty() { setDirty(true); setSaved(false) }

  function toggleChannel(id: string) {
    setChannels((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
    markDirty()
  }

  function toggleCategory(id: string) {
    setCategories((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
    markDirty()
  }

  async function handleSave() {
    setSaving(true)
    try {
      await saveUpdate({
        subscribeHot,
        minDiscountPercent: minDiscount === '' ? null : Number(minDiscount),
        maxAlertsPerDay: Number(maxAlerts) || 10,
        maxWatchAlertsPerDay: Number(maxWatchAlerts) || 5,
        channels,
        categories,
        hotLevel: hotLevel === '' ? null : hotLevel,
      })
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="portal-page">
      <h1 className="portal-page-title">Settings</h1>
      <p className="portal-page-sub">Configure your alert preferences.</p>

      {/* Hot deals */}
      <div className="settings-section">
        <div className="settings-section-title">Hot deals</div>
        <div className="settings-row">
          <div>
            <div className="settings-field-label">Subscribe to hot deals</div>
            <div className="settings-field-sub">Get alerts for deals that hit community hot thresholds.</div>
          </div>
          <button
            role="switch"
            aria-checked={subscribeHot}
            className={`toggle-btn ${subscribeHot ? 'toggle-btn-on' : 'toggle-btn-off'}`}
            onClick={() => { setSubscribeHot(!subscribeHot); markDirty() }}
            type="button"
          >
            <span className={`toggle-knob ${subscribeHot ? 'toggle-knob-on' : 'toggle-knob-off'}`} />
          </button>
        </div>
        <div className="settings-row" style={{ marginBottom: 0 }}>
          <div>
            <div className="settings-field-label">Hot deal level</div>
            <div className="settings-field-sub">Set how selective your hot alerts are. Top picks reach you across all categories; lower levels are filtered to your chosen categories.</div>
          </div>
          <select
            className="settings-number-input"
            value={hotLevel}
            disabled={!subscribeHot}
            onChange={(e) => { setHotLevel(e.target.value); markDirty() }}
          >
            {HOT_LEVEL_OPTIONS.map(({ id, label }) => (
              <option key={id || 'good'} value={id}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Discount threshold */}
      <div className="settings-section">
        <div className="settings-section-title">Discount threshold</div>
        <div className="settings-row">
          <div>
            <div className="settings-field-label">Minimum discount %</div>
            <div className="settings-field-sub">Leave blank to receive all deals regardless of discount.</div>
          </div>
          <input
            className="settings-number-input"
            type="number"
            min="0"
            max="100"
            placeholder="e.g. 20"
            value={minDiscount}
            onChange={(e) => { setMinDiscount(e.target.value); markDirty() }}
          />
        </div>
      </div>

      {/* Daily limits */}
      <div className="settings-section">
        <div className="settings-section-title">Daily limits</div>
        <div className="settings-row">
          <div>
            <div className="settings-field-label">Hot deal alerts / day</div>
          </div>
          <input
            className="settings-number-input"
            type="number"
            min="1"
            max="50"
            value={maxAlerts}
            onChange={(e) => { setMaxAlerts(e.target.value); markDirty() }}
          />
        </div>
        <div className="settings-row" style={{ marginBottom: 0 }}>
          <div>
            <div className="settings-field-label">Keyword alerts / day</div>
          </div>
          <input
            className="settings-number-input"
            type="number"
            min="1"
            max="50"
            value={maxWatchAlerts}
            onChange={(e) => { setMaxWatchAlerts(e.target.value); markDirty() }}
          />
        </div>
      </div>

      {/* Channels */}
      <div className="settings-section">
        <div className="settings-section-title">Alert channels</div>
        <div className="settings-checkbox-group">
          {CHANNEL_OPTIONS.map(({ id, label }) => (
            <label key={id} className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={channels.includes(id)}
                onChange={() => toggleChannel(id)}
              />
              <span className="settings-checkbox-label">{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Categories */}
      <div className="settings-section">
        <div className="settings-section-title">Deal categories</div>
        <div className="settings-field-sub" style={{ marginBottom: '16px' }}>Leave all unchecked to receive all categories.</div>
        <div className="settings-checkbox-group" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
          {CATEGORY_OPTIONS.map(({ id, label }) => (
            <label key={id} className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={categories.includes(id)}
                onChange={() => toggleCategory(id)}
              />
              <span className="settings-checkbox-label">{label}</span>
            </label>
          ))}
        </div>
      </div>

      {dirty && (
        <div className="save-bar">
          <span style={{ fontSize: '13px', color: 'rgba(232,233,236,0.4)' }}>You have unsaved changes.</span>
          <button className="btn-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      )}
      {saved && !dirty && (
        <div className="save-bar">
          <span className="save-status">Settings saved successfully.</span>
        </div>
      )}
    </div>
  )
}
