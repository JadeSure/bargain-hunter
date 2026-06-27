export interface Env {
  PORTAL_KV: KVNamespace
  NOTION_TOKEN: string
  SUBSCRIBERS_DB_ID: string
  WAITLIST_DB_ID: string
  RESEND_API_KEY: string
  WORKER_URL: string
  FRONTEND_URL: string
  OWNER_EMAIL: string
}

export interface SessionData {
  email: string
  name: string
  notionPageId: string
}

export interface WaitlistEntry {
  pageId: string
  email: string
  status: string
  source: string
  requestedAt: string | null
  lastSeen: string | null
  count: number
}

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
