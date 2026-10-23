'use client'

import { useState } from 'react'
import { useUser } from '../context'
import { createTelegramLink, refreshMe, unlinkTelegram } from '@/lib/api'

// ids must match the canonical Notion "Channels" multi-select values exactly
// (see valid set in portal-worker/src/routes/subscriber.ts) — lowercase ids
// here would never match, so the checkboxes would show unchecked even when
// the channel is actually on, and toggling would be silently dropped server-side.
const CHANNEL_OPTIONS = [
  { id: 'Email', label: 'Email' },
]

const REGION_OPTIONS = [
  { id: 'au', label: 'Australia' },
  { id: 'us', label: 'US & global (software, AI, USD deals)' },
  { id: 'cn', label: 'Mainland China (中国大陆)' },
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
  { id: 'digital', label: 'Software & Subscriptions' },
]

const HOT_LEVEL_OPTIONS = [
  { id: '', label: 'Good & up' },
  { id: 'great', label: 'Great & up' },
  { id: 'top', label: 'Top only' },
]

export default function SettingsPage() {
  const { user, setUser, saveUpdate } = useUser()

  const [subscribeHot, setSubscribeHot] = useState(user.subscribeHot)
  const [minDiscount, setMinDiscount] = useState<string>(
    user.minDiscountPercent != null ? String(user.minDiscountPercent) : ''
  )
  const [maxAlerts, setMaxAlerts] = useState<string>(String(user.maxAlertsPerDay))
  const [maxWatchAlerts, setMaxWatchAlerts] = useState<string>(String(user.maxWatchAlertsPerDay))
  const [channels, setChannels] = useState<string[]>(user.channels)
  const [categories, setCategories] = useState<string[]>(user.categories)
  const [regions, setRegions] = useState<string[]>(user.regions?.length ? user.regions : ['au'])
  const [hotLevel, setHotLevel] = useState<string>(user.hotLevel ?? '')
  const [quietCustom, setQuietCustom] = useState<boolean>(
    Boolean(user.quietHoursStart && user.quietHoursEnd)
  )
  const [quietStart, setQuietStart] = useState<string>(user.quietHoursStart ?? '22:00')
  const [quietEnd, setQuietEnd] = useState<string>(user.quietHoursEnd ?? '07:00')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [telegramUrl, setTelegramUrl] = useState<string | null>(null)
  const [telegramBusy, setTelegramBusy] = useState(false)
  const [telegramError, setTelegramError] = useState<string | null>(null)

  function markDirty() { setDirty(true); setSaved(false) }

  function toggleChannel(id: string) {
    setChannels((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
    markDirty()
  }

  function toggleCategory(id: string) {
    setCategories((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
    markDirty()
  }

  // Linking happens out-of-band: the user presses Start in Telegram and the bot
  // webhook writes the chat id to Notion, so we re-read /api/me afterwards.
  async function telegramAction(action: () => Promise<void>) {
    setTelegramBusy(true)
    setTelegramError(null)
    try {
      await action()
    } catch {
      setTelegramError('Something went wrong — please try again.')
    } finally {
      setTelegramBusy(false)
    }
  }

  const connectTelegram = () =>
    telegramAction(async () => setTelegramUrl(await createTelegramLink()))

  const checkTelegram = () =>
    telegramAction(async () => {
      const fresh = await refreshMe()
      setUser(fresh)
      if (fresh.telegramChatId) {
        setTelegramUrl(null)
        setChannels((prev) => (prev.includes('Telegram') ? prev : [...prev, 'Telegram']))
      } else {
        setTelegramError('Not connected yet — press Start in Telegram first.')
      }
    })

  const disconnectTelegram = () =>
    telegramAction(async () => {
      await unlinkTelegram()
      setUser({ ...user, telegramChatId: null, channels: user.channels.filter((c) => c !== 'Telegram') })
      setChannels((prev) => prev.filter((c) => c !== 'Telegram'))
    })

  async function handleSave() {
    setSaving(true)
    try {
      await saveUpdate({
        subscribeHot,
        minDiscountPercent: minDiscount === '' ? null : Number(minDiscount),
        maxAlertsPerDay: Number(maxAlerts) || 10,
        maxWatchAlertsPerDay: Number(maxWatchAlerts) || 5,
        channels,
        regions,
        categories,
        hotLevel: hotLevel === '' ? null : hotLevel,
        quietHoursStart: quietCustom && quietStart ? quietStart : null,
        quietHoursEnd: quietCustom && quietEnd ? quietEnd : null,
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
            <div className="settings-field-label">Recommended hot deals</div>
            <div className="settings-field-sub">On: community-hot deals plus your watch keywords. Off: only deals matching your watch keywords.</div>
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
            className="settings-select"
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
            <div className="settings-field-sub">Hot deals with a stated discount below this are skipped; deals with no stated discount still come through. Leave blank for no limit.</div>
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

      {/* Regions */}
      <div className="settings-section">
        <div className="settings-section-title">Regions</div>
        <div className="settings-field-sub" style={{ marginBottom: '16px' }}>Which regions&apos; deals you receive — applies to hot deals and keyword matches. Keep at least one ticked.</div>
        <div className="settings-checkbox-group">
          {REGION_OPTIONS.map(({ id, label }) => (
            <label key={id} className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={regions.includes(id)}
                disabled={regions.length === 1 && regions.includes(id)}
                onChange={() => { setRegions(regions.includes(id) ? regions.filter((r) => r !== id) : [...regions, id]); markDirty() }}
              />
              <span className="settings-checkbox-label">{label}</span>
            </label>
          ))}
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

      {/* Quiet hours */}
      <div className="settings-section">
        <div className="settings-section-title">Quiet hours</div>
        <div className="settings-row">
          <div>
            <div className="settings-field-label">Use custom quiet hours</div>
            <div className="settings-field-sub">
              No alerts are sent during quiet hours. Off = use the service default window.
            </div>
          </div>
          <button
            role="switch"
            aria-checked={quietCustom}
            className={`toggle-btn ${quietCustom ? 'toggle-btn-on' : 'toggle-btn-off'}`}
            onClick={() => { setQuietCustom(!quietCustom); markDirty() }}
            type="button"
          >
            <span className={`toggle-knob ${quietCustom ? 'toggle-knob-on' : 'toggle-knob-off'}`} />
          </button>
        </div>
        {quietCustom && (
          <div className="settings-row" style={{ marginBottom: 0 }}>
            <div>
              <div className="settings-field-label">Quiet from / until</div>
              <div className="settings-field-sub">
                Local Australian Eastern time. A window that ends before it starts wraps past
                midnight (e.g. 22:00 – 07:00).
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                className="settings-number-input"
                style={{ width: '110px', textAlign: 'left' }}
                type="time"
                value={quietStart}
                onChange={(e) => { setQuietStart(e.target.value); markDirty() }}
                aria-label="Quiet hours start"
              />
              <span style={{ fontSize: '13px', color: 'rgba(232,233,236,0.4)' }}>–</span>
              <input
                className="settings-number-input"
                style={{ width: '110px', textAlign: 'left' }}
                type="time"
                value={quietEnd}
                onChange={(e) => { setQuietEnd(e.target.value); markDirty() }}
                aria-label="Quiet hours end"
              />
            </div>
          </div>
        )}
      </div>

      {/* Channels */}
      <div className="settings-section">
        <div className="settings-section-title">Alert channels</div>
        <div className="settings-field-sub" style={{ marginBottom: '16px' }}>Untick to pause alerts on a channel (you can still log in and edit settings).</div>
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
          {user.telegramAvailable && user.telegramChatId && (
            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={channels.includes('Telegram')}
                onChange={() => toggleChannel('Telegram')}
              />
              <span className="settings-checkbox-label">Telegram (connected)</span>
            </label>
          )}
        </div>
        {user.telegramAvailable && (
          <div style={{ marginTop: '16px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
            {user.telegramChatId ? (
              <button className="btn-logout" onClick={disconnectTelegram} disabled={telegramBusy}>
                Disconnect Telegram
              </button>
            ) : telegramUrl ? (
              <>
                <a
                  className="btn-save"
                  href={telegramUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ textDecoration: 'none', display: 'inline-block' }}
                >
                  Open Telegram and press Start ↗
                </a>
                <button className="btn-logout" onClick={checkTelegram} disabled={telegramBusy}>
                  I&apos;ve pressed Start
                </button>
              </>
            ) : (
              <button className="btn-save" onClick={connectTelegram} disabled={telegramBusy}>
                Connect Telegram
              </button>
            )}
          </div>
        )}
        {telegramUrl && !user.telegramChatId && (
          <div className="settings-telegram-note">The link works once and expires in 15 minutes. Telegram alerts arrive faster than email; email keeps working alongside.</div>
        )}
        {telegramError && <div className="settings-telegram-note">{telegramError}</div>}
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
