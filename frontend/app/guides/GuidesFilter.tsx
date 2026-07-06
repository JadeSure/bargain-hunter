'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import type { Guide } from '@/lib/guides'
import { techniqueLabel } from '@/lib/guide-labels'

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
          <span className="guide-saving">Save {guide.total_est_saving}</span>
        )}
        {guide.difficulty && <span className="guide-meta-item">Difficulty: {guide.difficulty}</span>}
        <span className="guide-meta-item">{guide.steps.length} steps</span>
      </div>
    </Link>
  )
}

function guideSearchText(guide: Guide): string {
  return [
    guide.goal,
    guide.summary,
    ...guide.steps.map((s) => `${s.action} ${s.detail ?? ''}`),
  ]
    .join(' ')
    .toLowerCase()
}

export function GuidesFilter({
  guides,
  techniques,
  categories,
}: {
  guides: Guide[]
  techniques: string[]
  categories: string[]
}) {
  const [activeTechnique, setActiveTechnique] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  // Search corpora are derived once from the statically-embedded guide data.
  const searchTexts = useMemo(() => guides.map(guideSearchText), [guides])

  const trimmed = query.trim().toLowerCase()
  const terms = trimmed.length > 0 ? trimmed.split(/\s+/) : []

  const filtered = guides.filter((g, i) => {
    if (activeTechnique && !g.techniques.includes(activeTechnique)) return false
    if (activeCategory && g.category !== activeCategory) return false
    if (terms.length > 0 && !terms.every((t) => searchTexts[i].includes(t))) return false
    return true
  })

  const hasFilters = activeTechnique !== null || activeCategory !== null || terms.length > 0

  return (
    <>
      {guides.length > 0 && (
        <div className="guides-search">
          <input
            type="search"
            className="guides-search-input"
            placeholder="Search guides — e.g. gift cards, cashback, energy…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search guides"
          />
        </div>
      )}

      {categories.length > 0 && (
        <nav className="guides-filter" aria-label="Filter by category">
          <button
            className={`guide-filter-chip${!activeCategory ? ' guide-filter-chip-active' : ''}`}
            onClick={() => setActiveCategory(null)}
          >
            All categories
          </button>
          {categories.map((c) => (
            <button
              key={c}
              className={`guide-filter-chip${activeCategory === c ? ' guide-filter-chip-active' : ''}`}
              onClick={() => setActiveCategory(activeCategory === c ? null : c)}
            >
              {c}
            </button>
          ))}
        </nav>
      )}

      {techniques.length > 0 && (
        <nav className="guides-filter" aria-label="Filter by technique">
          <button
            className={`guide-filter-chip${!activeTechnique ? ' guide-filter-chip-active' : ''}`}
            onClick={() => setActiveTechnique(null)}
          >
            All
          </button>
          {techniques.map((t) => (
            <button
              key={t}
              className={`guide-filter-chip${activeTechnique === t ? ' guide-filter-chip-active' : ''}`}
              onClick={() => setActiveTechnique(activeTechnique === t ? null : t)}
            >
              {techniqueLabel(t)}
            </button>
          ))}
        </nav>
      )}

      {filtered.length === 0 ? (
        <div className="guides-empty">
          {guides.length === 0 ? (
            <>
              <p>Guides are on their way 🐑</p>
              <p className="guides-empty-sub">
                The scraper pulls discussions from OzBargain, Reddit, and Whirlpool daily — distilled guides will appear here as they&apos;re generated.
              </p>
            </>
          ) : hasFilters ? (
            <p>No guides match those filters — try broadening your search.</p>
          ) : (
            <p>No guides yet — check back soon.</p>
          )}
        </div>
      ) : (
        <div className="guides-grid">
          {filtered.map((g) => (
            <GuideCard key={g.id} guide={g} />
          ))}
        </div>
      )}
    </>
  )
}
