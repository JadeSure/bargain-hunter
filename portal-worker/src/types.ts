export interface Env {
  PORTAL_KV: KVNamespace
  NOTION_TOKEN: string
  SUBSCRIBERS_DB_ID: string
  WAITLIST_DB_ID: string
  RESEND_API_KEY: string
  WORKER_URL: string
  FRONTEND_URL: string
  OWNER_EMAIL: string
  UNSUBSCRIBE_HMAC_SECRET: string
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
  // "HH:MM" local time (run.timezone), or null to use the pipeline's global default.
  quietHoursStart: string | null
  quietHoursEnd: string | null
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
  quietHoursStart?: string | null
  quietHoursEnd?: string | null
}
