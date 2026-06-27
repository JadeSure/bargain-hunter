import Link from 'next/link'
import { BrandMark } from '../../components/BrandMark'

export default function CheckEmailPage() {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <BrandMark size={24} />
          <span className="login-logo-text">Bargain Hunter</span>
        </div>

        <div className="check-email-icon" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect width="48" height="48" rx="12" fill="rgba(249,115,22,0.12)" />
            <path d="M10 16.5C10 15.1 11.1 14 12.5 14h23c1.4 0 2.5 1.1 2.5 2.5v15c0 1.4-1.1 2.5-2.5 2.5h-23C11.1 34 10 32.9 10 31.5v-15z" stroke="#f97316" strokeWidth="1.8" fill="none" />
            <path d="M10 17l14 9 14-9" stroke="#f97316" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </div>

        <h1 className="login-h1">Check your email.</h1>
        <p className="login-sub">
          We&apos;ve sent a magic link. Click it to sign in — it expires in 15 minutes.
        </p>
        <p className="login-sub" style={{ marginTop: '0.5rem', opacity: 0.6, fontSize: '0.85rem' }}>
          Didn&apos;t get it? Check your spam folder, or{' '}
          <Link href="/login" className="login-link">try again</Link>.
        </p>

        <div className="login-action-row" style={{ marginTop: '2rem' }}>
          <Link href="/" className="login-link">← Back to home</Link>
        </div>
      </div>
    </div>
  )
}
