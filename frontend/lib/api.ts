export interface SubscriberData {
  name: string
  email: string
  telegramChatId: string | null
  subscribeHot: boolean
  watchKeywords: string[]
  blockKeywords: string[]
  minDiscountPercent: number | null
  maxAlertsPerDay: number
  maxWatchAlertsPerDay: number
  channels: string[]
  categories: string[]
  hotLevel: string | null
}

export interface SubscriberUpdate {
  subscribeHot?: boolean
  watchKeywords?: string[]
  blockKeywords?: string[]
  minDiscountPercent?: number | null
  maxAlertsPerDay?: number
  maxWatchAlertsPerDay?: number
  channels?: string[]
  categories?: string[]
  hotLevel?: string | null
}

const WORKER = process.env.NEXT_PUBLIC_WORKER_URL ?? ''

export async function requestAccess(email: string): Promise<void> {
  const res = await fetch(`${WORKER}/auth/request-access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(`${res.status}`)
}

export async function sendMagicLink(email: string): Promise<void> {
  const res = await fetch(`${WORKER}/auth/magic-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(`${res.status}`)
}

// Pass cookie string for server-side calls (forwards session cookie).
// Client-side calls omit cookie; the browser sends it automatically.
export async function getMe(cookie?: string): Promise<SubscriberData> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (cookie) headers['Cookie'] = cookie

  const res = await fetch(`${WORKER}/api/me`, {
    headers,
    credentials: 'include',
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json() as Promise<SubscriberData>
}

export async function updateMe(update: SubscriberUpdate): Promise<void> {
  // Relative URL → hits the frontend's same-origin /api proxy so the browser
  // sends the session cookie (which lives on the frontend domain, not the worker).
  const res = await fetch(`/api/me`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`${res.status}`)
}

export async function logout(cookie?: string): Promise<void> {
  const headers: Record<string, string> = {}
  if (cookie) headers['Cookie'] = cookie
  await fetch(`${WORKER}/auth/logout`, {
    method: 'POST',
    headers,
    credentials: 'include',
  }).catch(() => {})
}
