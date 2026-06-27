'use client'

import Link from 'next/link'
import { useState, useEffect, useRef, useCallback } from 'react'
import { requestAccess } from '@/lib/api'
import { BrandMark } from './components/BrandMark'

function ArrowRight() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M2 7.5H13M13 7.5L8.5 3M13 7.5L8.5 12" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function RequestAccessModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [inputError, setInputError] = useState(false)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  async function handleSubmit() {
    const val = email.trim()
    if (!val || !val.includes('@')) {
      setInputError(true)
      setTimeout(() => setInputError(false), 1200)
      inputRef.current?.focus()
      return
    }
    setLoading(true)
    try {
      await requestAccess(val)
    } catch {
      // always show success — prevent email enumeration
    } finally {
      setLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      onClick={onClose}
    >
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose} aria-label="Close">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M2 2L12 12M12 2L2 12" stroke="rgba(232,233,236,0.5)" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <div className="modal-head">
          <div className="modal-title" id="modal-title">Request Access</div>
          <div className="modal-sub">Drop your email below. We&apos;ll reach out when a spot opens — it&apos;s free.</div>
        </div>
        <div className="modal-field">
          <label className="modal-label" htmlFor="modal-email">Email address</label>
          <input
            ref={inputRef}
            className={`modal-input${inputError ? ' modal-input-error' : ''}`}
            type="email"
            id="modal-email"
            placeholder="you@example.com.au"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit() }}
          />
        </div>
        {submitted && (
          <div className="modal-success-banner" role="alert">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="8" cy="8" r="7" stroke="#4ade80" strokeWidth="1.4" />
              <path d="M5 8L7 10L11 6" stroke="#4ade80" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Request received — we&apos;ll be in touch!
          </div>
        )}
        <button
          className="btn-modal"
          onClick={handleSubmit}
          disabled={loading || submitted}
        >
          {submitted ? 'Requested' : loading ? 'Sending…' : 'Request Access'}
        </button>
        <div className="modal-disclaimer">Your email is only used to notify you about access.</div>
      </div>
    </div>
  )
}

export default function LandingPage() {
  const [showModal, setShowModal] = useState(false)
  const openModal = useCallback(() => setShowModal(true), [])
  const closeModal = useCallback(() => setShowModal(false), [])

  const tickerItems = [
    'OzBargain', 'CamelCamelCamel AU', 'Vote velocity scoring', 'Keyword matching',
    'Email alerts', 'Quiet hours (AEST)', 'Hot deal detection', 'Daily limits',
    'Block keywords', 'Runs every 5 minutes',
  ]

  return (
    <>
      {/* NAV */}
      <nav className="lp-nav" role="banner">
        <div className="lp-nav-logo">
          <BrandMark />
          <span className="lp-nav-logo-text">Bargain Hunter</span>
        </div>
        <div className="lp-nav-right">
          <Link className="lp-nav-link" href="/guides">Saving Guides</Link>
          <span className="lp-nav-tagline">Invite-only · Australia</span>
          <button className="btn-orange" onClick={openModal} aria-haspopup="dialog">
            Request Access
          </button>
        </div>
      </nav>

      {/* HERO */}
      <section className="lp-hero">
        <div className="lp-hero-bg" aria-hidden="true">
          <div className="lp-hero-glow1" />
          <div className="lp-hero-glow2" />
          <div className="lp-hero-grid" />
        </div>

        <div className="lp-hero-row">
          {/* Left */}
          <div className="lp-hero-left">
            <div className="lp-hero-eyebrow">
              <div className="live-dot" aria-hidden="true" />
              <span className="lp-eyebrow-text">Live · Scanning every 5 minutes</span>
            </div>
            <h1 className="lp-hero-h1">
              Catch every deal<br />
              <span className="lp-hero-h1-accent">before the crowd.</span>
            </h1>
            <p className="lp-hero-sub">
              Bargain Hunter monitors OzBargain and CamelCamelCamel AU every 5 minutes, scores trending deals by vote velocity, and sends personalised alerts — only for what you actually care about.
            </p>
            <div className="lp-hero-cta-row">
              <button className="btn-hero" onClick={openModal} aria-haspopup="dialog">
                Request Access <ArrowRight />
              </button>
              <span className="lp-cta-note">Free · No credit card</span>
            </div>
            <div className="lp-source-chips">
              <span className="lp-source-chips-label">Monitors:</span>
              <span className="lp-source-chip">OzBargain</span>
              <span className="lp-source-chip">CamelCamelCamel AU</span>
            </div>
          </div>

          {/* Right: card stack */}
          <div className="lp-hero-right">
            <div className="lp-scan-status">
              <div className="live-dot-sm" aria-hidden="true" />
              <span className="lp-scan-status-text">Scanning · last run 3 min ago</span>
            </div>
            <div className="lp-cards" aria-label="Sample deal alerts">

              {/* Card 1 – HOT DEAL (front) */}
              <div className="deal-card deal-card-hot">
                <div className="deal-card-topline deal-card-topline-orange" aria-hidden="true" />
                <div className="deal-card-header">
                  <span className="deal-card-badge deal-card-badge-orange">🔥 HOT DEAL</span>
                  <span className="deal-card-time">2 min ago</span>
                </div>
                <div className="deal-card-title">Sony WH-1000XM5 Wireless Headphones</div>
                <div className="deal-card-price-row">
                  <span className="deal-card-price deal-card-price-orange">$249</span>
                  <span className="deal-card-was">$499</span>
                  <span className="deal-card-discount deal-card-discount-orange">50% off</span>
                </div>
                <div className="deal-card-footer">
                  <svg width="11" height="10" viewBox="0 0 11 10" fill="none" aria-hidden="true">
                    <path d="M5.5 0.5L10 9H1L5.5 0.5Z" fill="#4ade80" />
                  </svg>
                  <span className="deal-card-votes">+42 votes · last hour</span>
                  <span className="deal-card-source">OzBargain</span>
                </div>
              </div>

              {/* Card 2 – WATCH MATCH (mid) */}
              <div className="deal-card deal-card-watch">
                <div className="deal-card-topline deal-card-topline-teal" aria-hidden="true" />
                <div className="deal-card-header">
                  <span className="deal-card-badge deal-card-badge-teal">◎ WATCH MATCH</span>
                  <span className="deal-card-time">8 min ago</span>
                </div>
                <div className="deal-card-title deal-card-title-sm">Dyson V15 Detect Total Home Vacuum</div>
                <div className="deal-card-match">↳ matched: &quot;Dyson ≤$600&quot;</div>
                <div className="deal-card-price-row deal-card-price-row-nomargin">
                  <span className="deal-card-price deal-card-price-teal">$559</span>
                  <span className="deal-card-was">$899</span>
                  <span className="deal-card-discount deal-card-discount-teal">38% off</span>
                </div>
              </div>

              {/* Card 3 – back */}
              <div className="deal-card deal-card-back">
                <div className="deal-card-topline deal-card-topline-orange" aria-hidden="true" />
                <div className="deal-card-header">
                  <span className="deal-card-badge deal-card-badge-orange">🔥 HOT DEAL</span>
                  <span className="deal-card-time">14 min ago</span>
                </div>
                <div className="deal-card-title">Samsung 27&quot; Odyssey OLED 4K Monitor</div>
                <div className="deal-card-price-row deal-card-price-row-nomargin">
                  <span className="deal-card-price deal-card-price-orange">$419</span>
                  <span className="deal-card-was">$699</span>
                  <span className="deal-card-discount deal-card-discount-orange">40% off</span>
                </div>
              </div>

            </div>
          </div>
        </div>
      </section>

      {/* TICKER */}
      <div className="lp-ticker" aria-hidden="true">
        <div className="lp-ticker-track">
          {[0, 1].map((i) => (
            <span key={i} className="lp-ticker-items">
              {tickerItems.map((item, j) => (
                <span key={j}>
                  <span>{item}</span>
                  <span className="lp-ticker-dot">◆</span>
                </span>
              ))}
            </span>
          ))}
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section className="lp-how">
        <div className="lp-section-inner">
          <div className="lp-how-head">
            <div className="lp-section-eyebrow">How it works</div>
            <h2>From feed to inbox in minutes.</h2>
          </div>
          <div className="lp-steps">

            <div className="lp-step-card">
              <div className="lp-step-num" aria-hidden="true">01</div>
              <div className="lp-step-body">
                <div className="lp-step-icon" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="2.5" fill="#f97316" />
                    <circle cx="12" cy="12" r="5.5" stroke="#f97316" strokeWidth="1.4" opacity="0.6" />
                    <circle cx="12" cy="12" r="9" stroke="#f97316" strokeWidth="1.4" opacity="0.28" />
                    <line x1="12" y1="12" x2="19.5" y2="4.5" stroke="#f97316" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </div>
                <h3>Deals detected</h3>
                <p>OzBargain and CamelCamelCamel AU are scanned every 5 minutes. Every new deal is captured with its vote count, price, and direct link.</p>
              </div>
            </div>

            <div className="lp-step-arrow" aria-hidden="true">
              <svg width="28" height="14" viewBox="0 0 28 14" fill="none">
                <path d="M0 7H22" stroke="#f97316" strokeWidth="1.4" strokeOpacity="0.35" />
                <path d="M18 2L24 7L18 12" stroke="#f97316" strokeWidth="1.4" strokeOpacity="0.35" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            <div className="lp-step-card">
              <div className="lp-step-num" aria-hidden="true">02</div>
              <div className="lp-step-body">
                <div className="lp-step-icon" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <path d="M3 17L8 11L12 14.5L17 8L21 11" stroke="#f97316" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M17 8H21V12" stroke="#f97316" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h3>Scored and filtered</h3>
                <p>Vote velocity scoring ranks deals by trending speed. Your keyword watch list is matched with optional price ceilings applied.</p>
              </div>
            </div>

            <div className="lp-step-arrow" aria-hidden="true">
              <svg width="28" height="14" viewBox="0 0 28 14" fill="none">
                <path d="M0 7H22" stroke="#f97316" strokeWidth="1.4" strokeOpacity="0.35" />
                <path d="M18 2L24 7L18 12" stroke="#f97316" strokeWidth="1.4" strokeOpacity="0.35" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            <div className="lp-step-card">
              <div className="lp-step-num" aria-hidden="true">03</div>
              <div className="lp-step-body">
                <div className="lp-step-icon" aria-hidden="true">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="5" width="20" height="14" rx="2.5" stroke="#f97316" strokeWidth="1.7" />
                    <path d="M2 8.5L12 14.5L22 8.5" stroke="#f97316" strokeWidth="1.7" strokeLinecap="round" />
                  </svg>
                </div>
                <h3>Alert delivered</h3>
                <p>A personalised digest lands in your inbox — price, discount, vote trend, direct link. One email per run, only when something worth it surfaces.</p>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="lp-features">
        <div className="lp-section-inner">
          <div className="lp-features-head">
            <div className="lp-section-eyebrow">Features</div>
            <h2>Built to cut through the noise.</h2>
          </div>
          <div className="lp-features-grid">

            <div className="lp-feat-card">
              <div className="lp-feat-glow-orange" aria-hidden="true" />
              <div className="lp-feat-icon lp-feat-icon-orange" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2C12 2 7 7.5 7 12C7 14.8 8.9 17.5 12 17.5C15.1 17.5 17 14.8 17 12C17 12 19.5 15.5 19.5 18.5C19.5 21.8 16.1 24.5 12 24.5C7.9 24.5 4.5 21.8 4.5 18.5C4.5 11 12 2 12 2Z" fill="#f97316" />
                </svg>
              </div>
              <h3>Hot deal detection</h3>
              <p>Vote velocity scoring identifies trending deals in real time. Early burst detection catches deals in the first 2 hours, before they sell out.</p>
            </div>

            <div className="lp-feat-card">
              <div className="lp-feat-glow-teal" aria-hidden="true" />
              <div className="lp-feat-icon lp-feat-icon-teal" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9.5" stroke="#2dd4bf" strokeWidth="1.6" />
                  <circle cx="12" cy="12" r="5" stroke="#2dd4bf" strokeWidth="1.6" />
                  <circle cx="12" cy="12" r="1.5" fill="#2dd4bf" />
                  <line x1="12" y1="1.5" x2="12" y2="5" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" />
                  <line x1="12" y1="19" x2="12" y2="22.5" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" />
                  <line x1="1.5" y1="12" x2="5" y2="12" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" />
                  <line x1="19" y1="12" x2="22.5" y2="12" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </div>
              <h3>Keyword watching</h3>
              <p>Set keywords with optional price ceilings — like <code className="lp-inline-code">Dyson ≤$600</code>. Alerted the moment a match surfaces.</p>
            </div>

            <div className="lp-feat-card">
              <div className="lp-feat-icon lp-feat-icon-neutral" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9.5" stroke="rgba(232,233,236,0.38)" strokeWidth="1.6" />
                  <line x1="6.8" y1="6.8" x2="17.2" y2="17.2" stroke="rgba(232,233,236,0.38)" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </div>
              <h3>Block keywords</h3>
              <p>Suppress deal categories you&apos;re not interested in. Block keywords are applied globally before matching, so your alerts stay relevant.</p>
            </div>

            <div className="lp-feat-card">
              <div className="lp-feat-icon lp-feat-icon-neutral" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="14" width="4" height="6" rx="1" fill="rgba(232,233,236,0.22)" />
                  <rect x="10" y="10" width="4" height="10" rx="1" fill="rgba(232,233,236,0.22)" />
                  <rect x="17" y="6" width="4" height="14" rx="1" fill="rgba(249,115,22,0.55)" />
                  <line x1="2" y1="4" x2="22" y2="4" stroke="#f97316" strokeWidth="1.4" strokeDasharray="3 2" strokeLinecap="round" />
                </svg>
              </div>
              <h3>Daily limits</h3>
              <p>Cap alerts per day, separately for hot deals and keyword watches. Prevents inbox overload on heavy deal days.</p>
            </div>

            <div className="lp-feat-card">
              <div className="lp-feat-icon lp-feat-icon-neutral" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke="rgba(232,233,236,0.42)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" />
                </svg>
              </div>
              <h3>Quiet hours</h3>
              <p>Define a window when alerts pause, respected in Australian Eastern Time. No 3am deal pings interrupting your sleep.</p>
            </div>

            <div className="lp-feat-card">
              <div className="lp-feat-glow-orange" aria-hidden="true" />
              <div className="lp-feat-icon lp-feat-icon-neutral" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M20 21V19C20 16.8 18.2 15 16 15H8C5.8 15 4 16.8 4 19V21" stroke="rgba(232,233,236,0.38)" strokeWidth="1.6" strokeLinecap="round" />
                  <circle cx="12" cy="9" r="4" stroke="rgba(232,233,236,0.38)" strokeWidth="1.6" />
                  <circle cx="18.5" cy="6" r="3" fill="#f97316" />
                  <path d="M17.5 6L18.2 6.7L19.8 5.2" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h3>Personalised digests</h3>
              <p>Every alert is tailored to you. Hot and watch matches merged into one clean digest — no spam, no repeated deals.</p>
            </div>

          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="lp-cta">
        <div className="lp-cta-inner">
          <div className="lp-cta-icon" aria-hidden="true">
            <BrandMark />
          </div>
          <h2>Ready to stop<br />missing deals?</h2>
          <p>Bargain Hunter is invite-only. Request access and we&apos;ll reach out when a spot opens — it&apos;s completely free.</p>
          <button className="btn-cta" onClick={openModal} aria-haspopup="dialog">
            Request Access <ArrowRight />
          </button>
          <div className="lp-cta-footnote">Free · No commitment · Australian shoppers</div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="lp-footer">
        <div className="lp-footer-row">
          <div className="lp-footer-logo">
            <BrandMark size={18} style={{ opacity: 0.7 }} />
            <span className="lp-footer-logo-text">Bargain Hunter</span>
          </div>
          <div className="lp-footer-text">Built for Australian shoppers · 2026</div>
          <div className="lp-footer-text">Powered by OzBargain &amp; CamelCamelCamel</div>
        </div>
      </footer>

      {showModal && <RequestAccessModal onClose={closeModal} />}
    </>
  )
}
