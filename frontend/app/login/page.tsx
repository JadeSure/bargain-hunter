'use client'

import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { sendMagicLink } from '@/lib/api'

function BrandLogo() {
  return (
    <svg width="24" height="24" viewBox="0 0 26 26" fill="none" aria-hidden="true">
      <path d="M13 1C13 1 7 7 7 12.5C7 15.8 9.2 18.5 13 18.5C16.8 18.5 19 15.8 19 12.5C19 12.5 21.5 16 21.5 19C21.5 22.7 17.6 25.5 13 25.5C8.4 25.5 4.5 22.7 4.5 19C4.5 11 13 1 13 1Z" fill="#f97316" />
      <path d="M13 14C13 14 11.2 15.8 11.2 17.5C11.2 18.7 12 19.6 13 19.6C14 19.6 14.8 18.7 14.8 17.5C14.8 15.8 13 14 13 14Z" fill="#fbbf24" />
    </svg>
  )
}

const ERROR_MESSAGES: Record<string, string> = {
  expired: 'That link has expired. Request a new one below.',
  invalid: 'Invalid link. Please try again.',
  not_found: 'That email isn\'t registered. You can request access from the home page.',
}

function LoginForm() {
  const searchParams = useSearchParams()
  const errorParam = searchParams.get('error') ?? ''
  const errorMessage = ERROR_MESSAGES[errorParam] ?? ''

  const router = useRouter()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const val = email.trim()
    if (!val || !val.includes('@')) return
    setLoading(true)
    try {
      await sendMagicLink(val)
    } catch {
      // always proceed — prevent enumeration
    } finally {
      setLoading(false)
      router.push('/login/check-email')
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <BrandLogo />
          <span className="login-logo-text">Bargain Hunter</span>
        </div>

        <h1 className="login-h1">Welcome back.</h1>
        <p className="login-sub">Enter your email and we&apos;ll send a magic link.</p>

        {errorMessage && (
          <div className="login-error-banner" role="alert">
            {errorMessage}
            {errorParam === 'not_found' && (
              <>
                {' '}
                <Link href="/" className="login-link">Request access →</Link>
              </>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label className="login-label" htmlFor="login-email">Email address</label>
          <input
            className="login-input"
            type="email"
            id="login-email"
            placeholder="you@example.com.au"
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <button className="btn-login" type="submit" disabled={loading}>
            {loading ? 'Sending…' : 'Send magic link'}
          </button>
        </form>

        <div className="login-action-row">
          <Link href="/" className="login-link">← Back to home</Link>
        </div>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="login-page" />}>
      <LoginForm />
    </Suspense>
  )
}
