import Link from 'next/link'
import type { Metadata } from 'next'
import { getGuides, getAllTechniques } from '@/lib/guides'
import { GuidesFilter } from './GuidesFilter'

export const metadata: Metadata = {
  title: 'Saving Guides · Bargain Hunter',
  description: 'Practical saving playbooks for Australian shoppers — cashback stacking, discounted gift cards, education stores, and more.',
}

function BrandLogo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" aria-hidden="true">
      <path d="M13 1C13 1 7 7 7 12.5C7 15.8 9.2 18.5 13 18.5C16.8 18.5 19 15.8 19 12.5C19 12.5 21.5 16 21.5 19C21.5 22.7 17.6 25.5 13 25.5C8.4 25.5 4.5 22.7 4.5 19C4.5 11 13 1 13 1Z" fill="#f97316" />
      <path d="M13 14C13 14 11.2 15.8 11.2 17.5C11.2 18.7 12 19.6 13 19.6C14 19.6 14.8 18.7 14.8 17.5C14.8 15.8 13 14 13 14Z" fill="#fbbf24" />
    </svg>
  )
}

export default async function GuidesPage() {
  const [guides, techniques] = await Promise.all([getGuides(), getAllTechniques()])

  return (
    <main className="guides-page">
      <header className="guides-header">
        <Link href="/" className="guides-brand">
          <BrandLogo />
          <span>Bargain Hunter</span>
        </Link>
        <Link href="/" className="guides-back">← Back to home</Link>
      </header>

      <section className="guides-hero">
        <h1 className="guides-hero-title">Saving Guides</h1>
        <p className="guides-hero-sub">
          Practical playbooks for Australian shoppers — cashback stacking, discounted gift cards, education stores, and more.
        </p>
      </section>

      <GuidesFilter guides={guides} techniques={techniques} />
    </main>
  )
}
