import Link from 'next/link'
import type { Metadata } from 'next'
import { getGiftCardDeals, giftCardExpiryLabel } from '@/lib/gift-cards'
import { BrandMark } from '../components/BrandMark'

export const metadata: Metadata = {
  title: 'Gift Card Deals · Bargain Hunter',
  description:
    'Discounted gift cards, cashback and bonus-points offers in Australia — stack them to knock 5–15% off almost anything. Updated regularly.',
  alternates: { canonical: '/gift-cards' },
  openGraph: {
    title: 'Gift Card Deals · Bargain Hunter',
    description:
      'Discounted gift cards, cashback and bonus-points offers in Australia — stack them to save on almost anything.',
    url: '/gift-cards',
  },
}

export default async function GiftCardsPage() {
  const deals = await getGiftCardDeals()

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
          <span>Discounted gift cards & cashback</span>
        </div>
        <h1 className="deals-hero-title">Gift Card Deals</h1>
        <p className="deals-hero-sub">
          Buy discounted gift cards and stack cashback to save 5–15% on almost anything — pay with
          a discounted card at checkout. Expired and upcoming offers are filtered out automatically.
        </p>
      </section>

      {deals.length === 0 ? (
        <section className="deals-empty">
          <div className="deals-empty-icon" aria-hidden="true">🎁</div>
          <p>No live gift-card deals right now. Check back soon.</p>
        </section>
      ) : (
        <section className="deals-grid-section">
          <div className="deals-count">{deals.length} live offer{deals.length !== 1 ? 's' : ''}</div>
          <div className="deals-grid">
            {deals.map((deal) => {
              const expiry = giftCardExpiryLabel(deal.expiry)
              return (
                <div key={deal.id} className="deal-live-card">
                  <div className="deal-live-top">
                    <div className="deal-live-badges">
                      {deal.valueHint && (
                        <span className="deals-badge deals-badge-giftcard">{deal.valueHint}</span>
                      )}
                      {deal.merchant && (
                        <span className="deals-badge deals-badge-source">{deal.merchant}</span>
                      )}
                    </div>
                    {expiry && <span className="deal-live-age">{expiry}</span>}
                  </div>

                  <h2 className="deal-live-title">
                    <a
                      href={deal.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="deal-live-link"
                    >
                      {deal.title}
                    </a>
                  </h2>

                  <div className="deal-live-footer">
                    <span className="deal-live-votes">
                      <svg width="10" height="9" viewBox="0 0 11 10" fill="none" aria-hidden="true">
                        <path d="M5.5 0.5L10 9H1L5.5 0.5Z" fill="#4ade80" />
                      </svg>
                      {deal.votesPos} votes
                      {deal.commentCount > 0 && <> · {deal.commentCount} comments</>}
                    </span>
                    <span className="deal-live-link-hint">View deal ↗</span>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}
    </main>
  )
}
