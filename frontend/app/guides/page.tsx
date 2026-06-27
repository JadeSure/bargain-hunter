import Link from 'next/link'
import type { Metadata } from 'next'
import { getGuides, getAllTechniques } from '@/lib/guides'
import { GuidesFilter } from './GuidesFilter'
import { BrandMark } from '../components/BrandMark'

export const metadata: Metadata = {
  title: 'Saving Guides',
  description:
    'Practical saving playbooks for Australian shoppers — cashback stacking, discounted gift cards, education stores, and more.',
  alternates: {
    canonical: '/guides',
  },
  openGraph: {
    title: 'Saving Guides · Bargain Hunter',
    description:
      'Practical saving playbooks for Australian shoppers — cashback stacking, discounted gift cards, education stores, and more.',
    url: '/guides',
  },
}

export default async function GuidesPage() {
  const [guides, techniques] = await Promise.all([getGuides(), getAllTechniques()])

  return (
    <main className="guides-page">
      <header className="guides-header">
        <Link href="/" className="guides-brand">
          <BrandMark size={24} />
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
