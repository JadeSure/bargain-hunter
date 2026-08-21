import Link from 'next/link'
import type { Metadata } from 'next'
import {
  getLeaderboard,
  topSavingsRates,
  topSignupBonuses,
  cheapestModels,
  categoryLabel,
  formatRate,
  formatUsdPerMillion,
  timeAgo,
} from '@/lib/leaderboard'
import type { BankProduct, LlmModel } from '@/lib/leaderboard'
import { BrandMark } from '../components/BrandMark'

export const metadata: Metadata = {
  title: 'Rates & Prices · Bargain Hunter',
  description:
    'The best Australian savings and term deposit rates, credit card signup bonuses, and cheapest LLM token prices — refreshed daily.',
  alternates: { canonical: '/rates' },
  openGraph: {
    title: 'Rates & Prices · Bargain Hunter',
    description:
      'Best AU savings/term deposit rates, credit card signup bonuses, and cheapest LLM token prices.',
    url: '/rates',
  },
}

function UpdatedChip({ label, iso }: { label: string; iso: string | null }) {
  return (
    <span className="rate-board-updated">
      {label} updated {timeAgo(iso)}
    </span>
  )
}

function BankRow({ rank, product, value }: { rank: number; product: BankProduct; value: string }) {
  return (
    <a href={product.url} target="_blank" rel="noopener noreferrer" className="rate-board-row">
      <span className="rate-board-rank">{rank}</span>
      <span className="rate-board-info">
        <span className="rate-board-name">{product.name}</span>
        <span className="rate-board-sub">
          <span className="deals-badge deals-badge-source">{product.brand}</span>
          <span className="rate-board-category">{categoryLabel(product.category)}</span>
        </span>
      </span>
      <span className="rate-board-value">{value}</span>
    </a>
  )
}

function ModelRow({ rank, model }: { rank: number; model: LlmModel }) {
  return (
    <a href={model.url} target="_blank" rel="noopener noreferrer" className="rate-board-row">
      <span className="rate-board-rank">{rank}</span>
      <span className="rate-board-info">
        <span className="rate-board-name">{model.name}</span>
        <span className="rate-board-sub">
          <span className="rate-board-category">{model.id}</span>
        </span>
      </span>
      <span className="rate-board-value">
        {formatUsdPerMillion(model.prompt_usd_per_token)}<span className="rate-board-unit">/M in</span>
      </span>
    </a>
  )
}

export default async function RatesPage() {
  const board = await getLeaderboard()
  const savings = topSavingsRates(board.bankProducts)
  const bonuses = topSignupBonuses(board.bankProducts)
  const { free, paid } = cheapestModels(board.llmModels)

  const empty = savings.length === 0 && bonuses.length === 0 && paid.length === 0

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
          <span>Standing leaderboard · refreshed roughly daily</span>
        </div>
        <h1 className="deals-hero-title">Rates &amp; Prices</h1>
        <p className="deals-hero-sub">
          Best AU savings and term deposit rates (from the government-mandated Consumer Data
          Right feed) and credit card signup bonuses, plus the cheapest LLM API token prices from
          OpenRouter. This tracks current standing values, not just changes.
        </p>
      </section>

      {empty ? (
        <section className="deals-empty">
          <div className="deals-empty-icon" aria-hidden="true">📊</div>
          <p>No leaderboard data yet. Check back after the next scheduled fetch.</p>
        </section>
      ) : (
        <>
          {savings.length > 0 && (
            <section className="deals-grid-section">
              <p className="portal-section-heading">Best savings &amp; term deposit rates</p>
              <UpdatedChip label="Bank data" iso={board.bankUpdatedAt} />
              <div className="rate-board-list">
                {savings.map((p, i) => (
                  <BankRow key={`${p.brand}-${p.name}`} rank={i + 1} product={p} value={formatRate(p.best_rate as number)} />
                ))}
              </div>
            </section>
          )}

          {bonuses.length > 0 && (
            <section className="deals-grid-section">
              <p className="portal-section-heading">Biggest credit card signup bonuses</p>
              <UpdatedChip label="Bank data" iso={board.bankUpdatedAt} />
              <div className="rate-board-list">
                {bonuses.map((p, i) => (
                  <BankRow
                    key={`${p.brand}-${p.name}`}
                    rank={i + 1}
                    product={p}
                    value={`${(p.bonus_points as number).toLocaleString()} pts`}
                  />
                ))}
              </div>
            </section>
          )}

          {paid.length > 0 && (
            <section className="deals-grid-section">
              <p className="portal-section-heading">Cheapest LLM token prices</p>
              <UpdatedChip label="Model prices" iso={board.llmUpdatedAt} />
              <div className="rate-board-list">
                {paid.map((m, i) => (
                  <ModelRow key={m.id} rank={i + 1} model={m} />
                ))}
              </div>
              {free.length > 0 && (
                <p className="rate-board-free-note">
                  Plus {free.length} free model{free.length !== 1 ? 's' : ''} (US$0/M tokens):{' '}
                  {free.map((m, i) => (
                    <span key={m.id}>
                      <a href={m.url} target="_blank" rel="noopener noreferrer">{m.name}</a>
                      {i < free.length - 1 ? ', ' : ''}
                    </span>
                  ))}
                </p>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}
