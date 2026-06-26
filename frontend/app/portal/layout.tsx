export const runtime = 'edge'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import Link from 'next/link'
import { getMe } from '@/lib/api'
import { UserProvider } from './context'
import { logoutAction } from './actions'
import type { ReactNode } from 'react'

export default async function PortalLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies()
  const session = cookieStore.get('session')?.value

  let user
  try {
    user = await getMe(session ? `session=${session}` : undefined)
  } catch (err: unknown) {
    const status = err instanceof Error ? err.message : ''
    if (status === '401' || status === '404') {
      redirect('/login')
    }
    throw err
  }

  const initials = user.name
    ? user.name.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()
    : user.email.slice(0, 2).toUpperCase()

  return (
    <UserProvider initial={user}>
      <div className="portal-shell">
        <nav className="portal-sidebar">
          <div className="portal-sidebar-logo">
            <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: '9px', textDecoration: 'none', color: 'inherit' }}>
              <svg width="22" height="22" viewBox="0 0 26 26" fill="none" aria-hidden="true">
                <path d="M13 1C13 1 7 7 7 12.5C7 15.8 9.2 18.5 13 18.5C16.8 18.5 19 15.8 19 12.5C19 12.5 21.5 16 21.5 19C21.5 22.7 17.6 25.5 13 25.5C8.4 25.5 4.5 22.7 4.5 19C4.5 11 13 1 13 1Z" fill="#f97316" />
                <path d="M13 14C13 14 11.2 15.8 11.2 17.5C11.2 18.7 12 19.6 13 19.6C14 19.6 14.8 18.7 14.8 17.5C14.8 15.8 13 14 13 14Z" fill="#fbbf24" />
              </svg>
              <span className="portal-sidebar-logo-text">Bargain Hunter</span>
            </Link>
          </div>

          <div className="portal-nav">
            <Link href="/portal" className="portal-nav-link">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
              </svg>
              Overview
            </Link>
            <Link href="/portal/keywords" className="portal-nav-link">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" />
              </svg>
              Keywords
            </Link>
            <Link href="/portal/settings" className="portal-nav-link">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
              </svg>
              Settings
            </Link>
          </div>

          <div className="portal-sidebar-footer">
            <div className="portal-user-info">
              <div className="portal-avatar-row">
                <div className="portal-avatar" aria-hidden="true">{initials}</div>
                <div>
                  <div className="portal-user-name">{user.name || 'You'}</div>
                  <div className="portal-user-email">{user.email}</div>
                </div>
              </div>
            </div>
            <form action={logoutAction}>
              <button type="submit" className="btn-logout">Sign out</button>
            </form>
          </div>
        </nav>

        <main className="portal-main">
          {children}
        </main>
      </div>
    </UserProvider>
  )
}
