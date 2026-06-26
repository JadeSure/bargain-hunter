import Link from 'next/link'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getGuide, getGuides, techniqueLabel } from '@/lib/guides'

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
  if (!guide) return { title: '攻略未找到 · Bargain Hunter' }
  return {
    title: `${guide.goal} · 薅羊毛攻略`,
    description: guide.summary,
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
          ← 攻略库
        </Link>
      </header>

      <article className="guide-article">
        <div className="guide-detail-techniques">
          {guide.techniques.map((t) => (
            <Link
              key={t}
              href={`/guides?technique=${encodeURIComponent(t)}`}
              className="guide-chip"
            >
              {techniqueLabel(t)}
            </Link>
          ))}
        </div>

        <h1 className="guide-detail-goal">{guide.goal}</h1>
        <p className="guide-detail-summary">{guide.summary}</p>

        <div className="guide-detail-facts">
          {guide.total_est_saving && (
            <div className="guide-fact">
              <span className="guide-fact-label">预计可省</span>
              <span className="guide-fact-value guide-saving">{guide.total_est_saving}</span>
            </div>
          )}
          {guide.difficulty && (
            <div className="guide-fact">
              <span className="guide-fact-label">难度</span>
              <span className="guide-fact-value">{guide.difficulty}</span>
            </div>
          )}
          <div className="guide-fact">
            <span className="guide-fact-label">地区</span>
            <span className="guide-fact-value">{guide.region}</span>
          </div>
          {guide.valid_until && (
            <div className="guide-fact">
              <span className="guide-fact-label">有效期至</span>
              <span className="guide-fact-value">{guide.valid_until.slice(0, 10)}</span>
            </div>
          )}
        </div>

        {guide.prerequisites.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">开始前你需要</h2>
            <ul className="guide-list">
              {guide.prerequisites.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="guide-section">
          <h2 className="guide-section-title">操作步骤</h2>
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
                        <span className="guide-step-tag guide-saving">省 {step.est_saving}</span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
          </ol>
        </section>

        {guide.risks.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">风险提示</h2>
            <ul className="guide-list guide-list-risk">
              {guide.risks.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        {guide.sources.length > 0 && (
          <section className="guide-section">
            <h2 className="guide-section-title">来源</h2>
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
            攻略由社区讨论自动提炼,价格与玩法可能随时变化,请以商家实际条款为准。
          </p>
        </footer>
      </article>
    </main>
  )
}
