'use client'

import { useUser } from './context'
import Link from 'next/link'

export default function PortalOverview() {
  const { user } = useUser()

  const greeting = (() => {
    const hour = new Date().getHours()
    if (hour < 12) return 'Good morning'
    if (hour < 17) return 'Good afternoon'
    return 'Good evening'
  })()

  const firstName = user.name?.split(' ')[0] || 'there'

  return (
    <div className="portal-page">
      <h1 className="portal-page-title">{greeting}, {firstName}.</h1>
      <p className="portal-page-sub">Here&apos;s your alert summary at a glance.</p>

      <div className="portal-stat-grid">
        <div className="portal-stat-card portal-stat-card--teal">
          <div className="portal-stat-label">Watch keywords</div>
          <div className="portal-stat-value">{user.watchKeywords.length}</div>
        </div>
        <div className="portal-stat-card">
          <div className="portal-stat-label">Block keywords</div>
          <div className="portal-stat-value">{user.blockKeywords.length}</div>
        </div>
        <div className="portal-stat-card portal-stat-card--orange">
          <div className="portal-stat-label">Max alerts / day</div>
          <div className="portal-stat-value">{user.maxAlertsPerDay}</div>
        </div>
        <div className="portal-stat-card portal-stat-card--green">
          <div className="portal-stat-label">Min discount</div>
          <div className="portal-stat-value">{user.minDiscountPercent != null ? `${user.minDiscountPercent}%` : 'Any'}</div>
        </div>
      </div>

      <div style={{ marginBottom: '8px', marginTop: '32px' }}>
        <p className="portal-section-heading">Quick actions</p>
      </div>
      <div className="portal-quick-links">
        <Link href="/portal/keywords" className="portal-quick-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" />
            <line x1="7" y1="7" x2="7.01" y2="7" />
          </svg>
          Manage keywords
        </Link>
        <Link href="/portal/settings" className="portal-quick-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
          </svg>
          Alert settings
        </Link>
      </div>

      {user.channels.length > 0 && (
        <div style={{ marginTop: '36px' }}>
          <p className="portal-section-heading">Active channels</p>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '12px' }}>
            {user.channels.map((ch) => (
              <span key={ch} className="status-chip status-chip-on">{ch}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
