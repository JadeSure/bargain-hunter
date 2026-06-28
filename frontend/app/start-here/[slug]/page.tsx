import Link from 'next/link'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { categoryLabel } from '@/lib/onboarding-labels'
import { getProgram, getPrograms } from '@/lib/onboarding'

export const dynamicParams = false

export async function generateStaticParams() {
  const programs = await getPrograms()
  return programs.map((p) => ({ slug: p.id }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const program = await getProgram(slug)
  if (!program) return { title: 'Program not found' }
  return {
    title: `${program.name} · Start Here`,
    description: program.one_liner,
    alternates: {
      canonical: `/start-here/${program.id}`,
    },
    openGraph: {
      title: `${program.name} · Start Here`,
      description: program.one_liner,
      url: `/start-here/${program.id}`,
      type: 'article',
      locale: 'en_AU',
    },
    twitter: {
      card: 'summary',
      title: `${program.name} · Start Here`,
      description: program.one_liner,
    },
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export default async function ProgramDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const program = await getProgram(slug)
  if (!program) notFound()

  return (
    <main className="guide-detail">
      <header className="guides-header">
        <Link href="/start-here" className="guides-brand">
          ← Start Here
        </Link>
      </header>

      <article className="guide-article">
        <div className="guide-detail-techniques">
          <span className="guide-chip">{categoryLabel(program.category)}</span>
          {program.needs_referral && (
            <span className="guide-chip program-referral-chip">Referral needed</span>
          )}
        </div>

        <h1 className="guide-detail-goal">{program.name}</h1>
        <p className="guide-detail-summary">{program.one_liner}</p>

        <div className="guide-detail-facts">
          {program.signup_bonus && (
            <div className="guide-fact">
              <span className="guide-fact-label">Sign-up bonus</span>
              <span className="guide-fact-value guide-saving">{program.signup_bonus}</span>
            </div>
          )}
          {program.est_value && (
            <div className="guide-fact">
              <span className="guide-fact-label">Est. value</span>
              <span className="guide-fact-value guide-saving">{program.est_value}</span>
            </div>
          )}
          <div className="guide-fact">
            <span className="guide-fact-label">Region</span>
            <span className="guide-fact-value">{program.region}</span>
          </div>
          {program.valid_until && (
            <div className="guide-fact">
              <span className="guide-fact-label">Valid until</span>
              <span className="guide-fact-value">{program.valid_until.slice(0, 10)}</span>
            </div>
          )}
        </div>

        <section className="guide-section">
          <h2 className="guide-section-title">What you get</h2>
          <p className="guide-detail-summary">{program.benefit}</p>
        </section>

        {program.prerequisites.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Before you start</h2>
            <ul className="guide-list">
              {program.prerequisites.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="guide-section">
          <h2 className="guide-section-title">How to join</h2>
          <ol className="guide-steps">
            {[...program.how_to_join]
              .sort((a, b) => a.order - b.order)
              .map((step) => (
                <li key={step.order} className="guide-step">
                  <div className="guide-step-num">{step.order}</div>
                  <div className="guide-step-body">
                    <div className="guide-step-action">{step.action}</div>
                    {step.detail && <p className="guide-step-detail">{step.detail}</p>}
                  </div>
                </li>
              ))}
          </ol>
        </section>

        {program.needs_referral && program.referral_note && (
          <div className="program-referral-callout">
            <strong>💡 Referral tip</strong>
            <p>{program.referral_note}</p>
          </div>
        )}

        {program.risks.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Risks</h2>
            <ul className="guide-list guide-list-risk">
              {program.risks.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        {program.official_url && (
          <section className="guide-section">
            <a
              href={program.official_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="program-official-btn"
            >
              Visit official site ↗
            </a>
          </section>
        )}

        {program.sources.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Sources</h2>
            <ul className="guide-sources">
              {program.sources.map((url, i) => (
                <li key={i}>
                  <a href={url} target="_blank" rel="noopener noreferrer nofollow">
                    {hostOf(url)} ↗
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        <footer className="guide-footer">
          <p className="guide-disclaimer">
            Program details, bonus amounts, and eligibility conditions change frequently — always check the official site for current terms before signing up.
          </p>
        </footer>
      </article>
    </main>
  )
}
