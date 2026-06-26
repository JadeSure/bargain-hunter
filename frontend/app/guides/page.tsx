import Link from 'next/link'
import type { Metadata } from 'next'
import { getGuides, getAllTechniques, techniqueLabel, type Guide } from '@/lib/guides'

export const metadata: Metadata = {
  title: '薅羊毛攻略 · Bargain Hunter',
  description: '把澳洲论坛里散落的组合省钱玩法,提炼成可照做的攻略——返现、折扣礼品卡、教育优惠等技巧的组合拳。',
}

function BrandLogo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" aria-hidden="true">
      <path d="M13 1C13 1 7 7 7 12.5C7 15.8 9.2 18.5 13 18.5C16.8 18.5 19 15.8 19 12.5C19 12.5 21.5 16 21.5 19C21.5 22.7 17.6 25.5 13 25.5C8.4 25.5 4.5 22.7 4.5 19C4.5 11 13 1 13 1Z" fill="#f97316" />
      <path d="M13 14C13 14 11.2 15.8 11.2 17.5C11.2 18.7 12 19.6 13 19.6C14 19.6 14.8 18.7 14.8 17.5C14.8 15.8 13 14 13 14Z" fill="#fbbf24" />
    </svg>
  )
}

function GuideCard({ guide }: { guide: Guide }) {
  return (
    <Link href={`/guides/${guide.id}`} className="guide-card">
      <div className="guide-card-goal">{guide.goal}</div>
      <p className="guide-card-summary">{guide.summary}</p>
      <div className="guide-card-techniques">
        {guide.techniques.slice(0, 5).map((t) => (
          <span key={t} className="guide-chip">
            {techniqueLabel(t)}
          </span>
        ))}
      </div>
      <div className="guide-card-meta">
        {guide.total_est_saving && (
          <span className="guide-saving">省 {guide.total_est_saving}</span>
        )}
        {guide.difficulty && <span className="guide-meta-item">难度 {guide.difficulty}</span>}
        <span className="guide-meta-item">{guide.steps.length} 步</span>
      </div>
    </Link>
  )
}

export default async function GuidesPage({
  searchParams,
}: {
  searchParams: Promise<{ technique?: string }>
}) {
  const { technique } = await searchParams
  const [guides, techniques] = await Promise.all([getGuides(), getAllTechniques()])
  const filtered = technique
    ? guides.filter((g) => g.techniques.includes(technique))
    : guides

  return (
    <main className="guides-page">
      <header className="guides-header">
        <Link href="/" className="guides-brand">
          <BrandLogo />
          <span>Bargain Hunter</span>
        </Link>
        <Link href="/" className="guides-back">← 返回首页</Link>
      </header>

      <section className="guides-hero">
        <h1 className="guides-hero-title">薅羊毛攻略库</h1>
        <p className="guides-hero-sub">
          把澳洲论坛里散落的组合省钱玩法,提炼成照着做就行的攻略。
        </p>
      </section>

      {techniques.length > 0 && (
        <nav className="guides-filter" aria-label="按技巧筛选">
          <Link
            href="/guides"
            className={`guide-filter-chip${!technique ? ' guide-filter-chip-active' : ''}`}
          >
            全部
          </Link>
          {techniques.map((t) => (
            <Link
              key={t}
              href={`/guides?technique=${encodeURIComponent(t)}`}
              className={`guide-filter-chip${technique === t ? ' guide-filter-chip-active' : ''}`}
            >
              {techniqueLabel(t)}
            </Link>
          ))}
        </nav>
      )}

      {filtered.length === 0 ? (
        <div className="guides-empty">
          {guides.length === 0 ? (
            <>
              <p>攻略正在路上 🐑</p>
              <p className="guides-empty-sub">
                采集器每天从 OzBargain / Reddit / Whirlpool 抓取讨论,提炼后的攻略会陆续出现在这里。
              </p>
            </>
          ) : (
            <p>该技巧下暂时没有攻略,换一个试试。</p>
          )}
        </div>
      ) : (
        <div className="guides-grid">
          {filtered.map((g) => (
            <GuideCard key={g.id} guide={g} />
          ))}
        </div>
      )}
    </main>
  )
}
