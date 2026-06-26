import Link from 'next/link'

export default function CheckEmailPage() {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <svg width="24" height="24" viewBox="0 0 26 26" fill="none" aria-hidden="true">
            <path d="M13 1C13 1 7 7 7 12.5C7 15.8 9.2 18.5 13 18.5C16.8 18.5 19 15.8 19 12.5C19 12.5 21.5 16 21.5 19C21.5 22.7 17.6 25.5 13 25.5C8.4 25.5 4.5 22.7 4.5 19C4.5 11 13 1 13 1Z" fill="#f97316" />
            <path d="M13 14C13 14 11.2 15.8 11.2 17.5C11.2 18.7 12 19.6 13 19.6C14 19.6 14.8 18.7 14.8 17.5C14.8 15.8 13 14 13 14Z" fill="#fbbf24" />
          </svg>
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
