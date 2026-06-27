import Link from 'next/link'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { techniqueLabel } from '@/lib/guide-labels'
import { getGuide, getGuides } from '@/lib/guides'

export const dynamicParams = false

export async function generateStaticParams() {
  const guides = await getGuides()
  return guides.map((g) => ({ slug: g.id }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const guide = await getGuide(slug)
  if (!guide) return { title: 'Guide not found' }
  return {
    title: `${guide.goal} · Saving Guides`,
    description: guide.summary,
    alternates: {
      canonical: `/guides/${guide.id}`,
    },
    openGraph: {
      title: `${guide.goal} · Saving Guides`,
      description: guide.summary,
      url: `/guides/${guide.id}`,
      type: 'article',
      locale: 'en_AU',
    },
    twitter: {
      card: 'summary',
      title: `${guide.goal} · Saving Guides`,
      description: guide.summary,
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

export default async function GuideDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const guide = await getGuide(slug)
  if (!guide) notFound()

  return (
    <main className="guide-detail">
      <header className="guides-header">
        <Link href="/guides" className="guides-brand">
          ← Guides
        </Link>
      </header>

      <article className="guide-article">
        <div className="guide-detail-techniques">
          {guide.techniques.map((t) => (
            <span key={t} className="guide-chip">
              {techniqueLabel(t)}
            </span>
          ))}
        </div>

        <h1 className="guide-detail-goal">{guide.goal}</h1>
        <p className="guide-detail-summary">{guide.summary}</p>

        <div className="guide-detail-facts">
          {guide.total_est_saving && (
            <div className="guide-fact">
              <span className="guide-fact-label">Est. saving</span>
              <span className="guide-fact-value guide-saving">{guide.total_est_saving}</span>
            </div>
          )}
          {guide.difficulty && (
            <div className="guide-fact">
              <span className="guide-fact-label">Difficulty</span>
              <span className="guide-fact-value">{guide.difficulty}</span>
            </div>
          )}
          <div className="guide-fact">
            <span className="guide-fact-label">Region</span>
            <span className="guide-fact-value">{guide.region}</span>
          </div>
          {guide.valid_until && (
            <div className="guide-fact">
              <span className="guide-fact-label">Valid until</span>
              <span className="guide-fact-value">{guide.valid_until.slice(0, 10)}</span>
            </div>
          )}
        </div>

        {guide.prerequisites.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Before you start</h2>
            <ul className="guide-list">
              {guide.prerequisites.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="guide-section">
          <h2 className="guide-section-title">Steps</h2>
          <ol className="guide-steps">
            {[...guide.steps]
              .sort((a, b) => a.order - b.order)
              .map((step) => (
                <li key={step.order} className="guide-step">
                  <div className="guide-step-num">{step.order}</div>
                  <div className="guide-step-body">
                    <div className="guide-step-action">{step.action}</div>
                    {step.detail && <p className="guide-step-detail">{step.detail}</p>}
                    <div className="guide-step-tags">
                      {step.technique && (
                        <span className="guide-step-tag">{techniqueLabel(step.technique)}</span>
                      )}
                      {step.est_saving && (
                        <span className="guide-step-tag guide-saving">Save {step.est_saving}</span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
          </ol>
        </section>

        {guide.risks.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Risks</h2>
            <ul className="guide-list guide-list-risk">
              {guide.risks.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        {guide.sources.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">Sources</h2>
            <ul className="guide-sources">
              {guide.sources.map((url, i) => (
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
            Guides are generated automatically from community discussions. Prices and mechanics can change — always check the retailer&apos;s current terms.
          </p>
        </footer>
      </article>
    </main>
  )
}
