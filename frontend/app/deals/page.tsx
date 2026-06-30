import Link from 'next/link'
import type { Metadata } from 'next'
import { getLiveDeals, formatAge, sourceLabel } from '@/lib/deals'
import { BrandMark } from '../components/BrandMark'

export const metadata: Metadata = {
  title: 'Hot Deals · Bargain Hunter',
  description: 'Currently available hot deals in Australia, scored by vote velocity. Updated every 30 minutes.',
  alternates: { canonical: '/deals' },
  openGraph: {
    title: 'Hot Deals · Bargain Hunter',
    description: 'Currently available hot deals in Australia, scored by vote velocity.',
    url: '/deals',
  },
}

function HotLevelBadge({ level }: { level: string | null }) {
  if (!level) return null
  const labels: Record<string, string> = { top: '🔥 Top', great: '⚡ Great', good: '✅ Good' }
  const classes: Record<string, string> = {
    top: 'deals-badge-top',
    great: 'deals-badge-great',
    good: 'deals-badge-good',
  }
  return (
    <span className={`deals-badge ${classes[level] ?? 'deals-badge-good'}`}>
      {labels[level] ?? level}
    </span>
  )
}

function SourceBadge({ source }: { source: string }) {
  return <span className="deals-badge deals-badge-source">{sourceLabel(source)}</span>
}

export default async function DealsPage() {
  const deals = await getLiveDeals()

  return (
    <main className="deals-page">
      <header className="deals-header">
        <div className="deals-header-inner">
          <Link href="/" className="deals-brand">
            <BrandMark size={24} />
            <span>Bargain Hunter</span>
          </Link>
          <Link href="/" className="deals-back">← Back to home</Link>
        </div>
      </header>

      <section className="deals-hero">
        <div className="deals-hero-eyebrow">
          <div className="live-dot" aria-hidden="true" />
          <span>Live deals · refreshed every 30 min</span>
        </div>
        <h1 className="deals-hero-title">Hot Deals Right Now</h1>
        <p className="deals-hero-sub">
          Deals scored by vote velocity — only what&apos;s trending. Expired deals are removed automatically.
        </p>
      </section>

      {deals.length === 0 ? (
        <section className="deals-empty">
          <div className="deals-empty-icon" aria-hidden="true">🔍</div>
          <p>No hot deals detected in the latest scan. Check back in a few minutes.</p>
        </section>
      ) : (
        <section className="deals-grid-section">
          <div className="deals-count">{deals.length} active deal{deals.length !== 1 ? 's' : ''}</div>
          <div className="deals-grid">
            {deals.map((deal) => (
              <a
                key={deal.key}
                href={deal.url}
                target="_blank"
                rel="noopener noreferrer"
                className="deal-live-card"
              >
                <div className="deal-live-top">
                  <div className="deal-live-badges">
                    <HotLevelBadge level={deal.hotLevel} />
                    <SourceBadge source={deal.source} />
                  </div>
                  <span className="deal-live-age">{formatAge(deal.ageHours)}</span>
                </div>

                <h2 className="deal-live-title">{deal.title}</h2>

                {(deal.price !== null || deal.discountPercent !== null) && (
                  <div className="deal-live-meta">
                    {deal.price !== null && (
                      <span className="deal-live-price">${deal.price.toFixed(2)}</span>
                    )}
                    {deal.discountPercent !== null && (
                      <span className="deal-live-discount">{Math.round(deal.discountPercent)}% off</span>
                    )}
                  </div>
                )}

                <div className="deal-live-footer">
                  {deal.source === 'ozbargain' && (
                    <span className="deal-live-votes">
                      <svg width="10" height="9" viewBox="0 0 11 10" fill="none" aria-hidden="true">
                        <path d="M5.5 0.5L10 9H1L5.5 0.5Z" fill="#4ade80" />
                      </svg>
                      {deal.votesPos} votes
                      {deal.commentCount > 0 && <> · {deal.commentCount} comments</>}
                    </span>
                  )}
                  <span className="deal-live-score">peak {deal.peakScore.toFixed(2)}</span>
                  <span className="deal-live-link-hint">View deal ↗</span>
                </div>
              </a>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
