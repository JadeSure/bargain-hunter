import Link from 'next/link'
import type { Metadata } from 'next'
import { getPrograms, getAllCategories } from '@/lib/onboarding'
import { StartHereFilter } from './StartHereFilter'
import { BrandMark } from '../components/BrandMark'

export const metadata: Metadata = {
  title: 'Start Here · New to Australia',
  description:
    'New to Australia? Join these programs to start saving — cashback portals, high-interest banks, loyalty programs, and referral bonuses.',
  alternates: {
    canonical: '/start-here',
  },
  openGraph: {
    title: 'Start Here · New to Australia · Bargain Hunter',
    description:
      'New to Australia? Join these programs to start saving — cashback portals, high-interest banks, loyalty programs, and referral bonuses.',
    url: '/start-here',
  },
}

export default async function StartHerePage() {
  const [programs, categories] = await Promise.all([getPrograms(), getAllCategories()])

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
        <h1 className="guides-hero-title">New to Australia? Start Here</h1>
        <p className="guides-hero-sub">
          Join these programs to start saving from day one — cashback portals, high-interest bank accounts, loyalty points, and referral bonuses.
        </p>
      </section>

      <StartHereFilter programs={programs} categories={categories} />
    </main>
  )
}
