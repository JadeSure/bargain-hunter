'use client'

import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { sendMagicLink } from '@/lib/api'
import { BrandMark } from '../components/BrandMark'

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
          <BrandMark size={24} />
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
