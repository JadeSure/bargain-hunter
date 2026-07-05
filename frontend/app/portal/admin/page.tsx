'use client'

import { useCallback, useEffect, useState } from 'react'

interface WaitlistEntry {
  pageId: string
  email: string
  status: string
  source: string
  requestedAt: string | null
  lastSeen: string | null
  count: number
}

type LoadState = 'loading' | 'ready' | 'forbidden' | 'error'

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function AdminPage() {
  const [state, setState] = useState<LoadState>('loading')
  const [entries, setEntries] = useState<WaitlistEntry[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')

  const load = useCallback(async () => {
    try {
      // Same-origin proxy (/api/[...path]) forwards the session cookie to the
      // worker's owner-only GET /api/admin/waitlist.
      const res = await fetch('/api/admin/waitlist', { credentials: 'include' })
      if (res.status === 403) { setState('forbidden'); return }
      if (!res.ok) { setState('error'); return }
      const data = (await res.json()) as { waitlist: WaitlistEntry[] }
      setEntries(data.waitlist)
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function act(action: 'approve' | 'reject', email: string) {
    setBusy(email)
    setActionError('')
    try {
      const res = await fetch(`/api/admin/waitlist/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        setActionError(`Could not ${action} ${email} (HTTP ${res.status}).`)
        return
      }
      setEntries((prev) => prev.filter((e) => e.email !== email))
    } catch {
      setActionError(`Could not ${action} ${email} — network error.`)
    } finally {
      setBusy(null)
    }
  }

  if (state === 'loading') {
    return (
      <div className="portal-page">
        <h1 className="portal-page-title">Admin</h1>
        <p className="portal-page-sub">Loading waitlist…</p>
      </div>
    )
  }

  if (state === 'forbidden') {
    return (
      <div className="portal-page">
        <h1 className="portal-page-title">Not authorised</h1>
        <p className="portal-page-sub">This page is only available to the site owner.</p>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="portal-page">
        <h1 className="portal-page-title">Admin</h1>
        <p className="portal-page-sub">Something went wrong loading the waitlist. Try refreshing.</p>
      </div>
    )
  }

  return (
    <div className="portal-page">
      <h1 className="portal-page-title">Admin</h1>
      <p className="portal-page-sub">
        {entries.length === 0
          ? 'No pending access requests.'
          : `${entries.length} pending access request${entries.length !== 1 ? 's' : ''}. Approving sends the applicant a login link; rejecting is silent.`}
      </p>

      {actionError && (
        <p role="alert" style={{ color: '#f87171', fontSize: '13px', marginBottom: '16px' }}>{actionError}</p>
      )}

      {entries.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            <thead>
              <tr style={{ textAlign: 'left', opacity: 0.55 }}>
                <th style={{ padding: '8px 12px 8px 0', fontWeight: 500 }}>Email</th>
                <th style={{ padding: '8px 12px 8px 0', fontWeight: 500 }}>Requested</th>
                <th style={{ padding: '8px 12px 8px 0', fontWeight: 500 }}>Requests</th>
                <th style={{ padding: '8px 0', fontWeight: 500 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.pageId} style={{ borderTop: '1px solid rgba(232,233,236,0.08)' }}>
                  <td style={{ padding: '12px 12px 12px 0' }}>{e.email}</td>
                  <td style={{ padding: '12px 12px 12px 0', whiteSpace: 'nowrap' }}>{formatDate(e.requestedAt)}</td>
                  <td style={{ padding: '12px 12px 12px 0' }}>{e.count}</td>
                  <td style={{ padding: '12px 0', whiteSpace: 'nowrap' }}>
                    <button
                      className="btn-save"
                      style={{ marginRight: '8px' }}
                      disabled={busy !== null}
                      onClick={() => act('approve', e.email)}
                    >
                      {busy === e.email ? 'Working…' : 'Approve'}
                    </button>
                    <button
                      className="btn-logout"
                      disabled={busy !== null}
                      onClick={() => act('reject', e.email)}
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
