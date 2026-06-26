'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { Guide } from '@/lib/guides'
import { techniqueLabel } from '@/lib/guides'

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

export function GuidesFilter({
  guides,
  techniques,
}: {
  guides: Guide[]
  techniques: string[]
}) {
  const [active, setActive] = useState<string | null>(null)
  const filtered = active ? guides.filter((g) => g.techniques.includes(active)) : guides

  return (
    <>
      {techniques.length > 0 && (
        <nav className="guides-filter" aria-label="Filter by technique">
          <button
            className={`guide-filter-chip${!active ? ' guide-filter-chip-active' : ''}`}
            onClick={() => setActive(null)}
          >
            All
          </button>
          {techniques.map((t) => (
            <button
              key={t}
              className={`guide-filter-chip${active === t ? ' guide-filter-chip-active' : ''}`}
              onClick={() => setActive(active === t ? null : t)}
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
          ) : (
            <p>No guides for that technique yet — try another.</p>
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
