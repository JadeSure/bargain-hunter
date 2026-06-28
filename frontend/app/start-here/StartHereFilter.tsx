'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { Program } from '@/lib/onboarding'
import { categoryLabel } from '@/lib/onboarding-labels'

function ProgramCard({ program }: { program: Program }) {
  return (
    <Link href={`/start-here/${program.id}`} className="guide-card">
      <div className="guide-card-goal">{program.name}</div>
      <p className="guide-card-summary">{program.one_liner}</p>
      <div className="guide-card-techniques">
        <span className="guide-chip">{categoryLabel(program.category)}</span>
        {program.needs_referral && (
          <span className="guide-chip program-referral-chip">Referral needed</span>
        )}
      </div>
      <div className="guide-card-meta">
        {program.signup_bonus && (
          <span className="guide-saving">{program.signup_bonus}</span>
        )}
        {!program.signup_bonus && program.est_value && (
          <span className="guide-saving">{program.est_value}</span>
        )}
      </div>
    </Link>
  )
}

export function StartHereFilter({
  programs,
  categories,
}: {
  programs: Program[]
  categories: string[]
}) {
  const [active, setActive] = useState<string | null>(null)
  const filtered = active ? programs.filter((p) => p.category === active) : programs

  return (
    <>
      {categories.length > 0 && (
        <nav className="guides-filter" aria-label="Filter by category">
          <button
            className={`guide-filter-chip${!active ? ' guide-filter-chip-active' : ''}`}
            onClick={() => setActive(null)}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              className={`guide-filter-chip${active === c ? ' guide-filter-chip-active' : ''}`}
              onClick={() => setActive(active === c ? null : c)}
            >
              {categoryLabel(c)}
            </button>
          ))}
        </nav>
      )}

      {filtered.length === 0 ? (
        <div className="guides-empty">
          {programs.length === 0 ? (
            <>
              <p>Catalog coming soon 🐑</p>
              <p className="guides-empty-sub">
                The onboarding program catalog will appear here once it&apos;s generated.
              </p>
            </>
          ) : (
            <p>No programs in that category yet — try another.</p>
          )}
        </div>
      ) : (
        <div className="guides-grid">
          {filtered.map((p) => (
            <ProgramCard key={p.id} program={p} />
          ))}
        </div>
      )}
    </>
  )
}
