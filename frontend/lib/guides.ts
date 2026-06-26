import { promises as fs } from 'fs'
import path from 'path'

// Mirrors the Python `Guide` pydantic model (src/strategy_hunter/models.py).
// Guides are produced in Stage 2 and stored as JSON in the repo; this module
// reads them at build time so the /guides pages can be statically generated.

export interface GuideStep {
  order: number
  action: string
  detail?: string | null
  est_saving?: string | null
  technique?: string | null
}

export interface Guide {
  id: string
  goal: string
  category?: string | null
  region: string
  summary: string
  techniques: string[]
  steps: GuideStep[]
  total_est_saving?: string | null
  difficulty?: string | null
  risks: string[]
  prerequisites: string[]
  sources: string[]
  valid_until?: string | null
  confidence?: number | null
  generated_at?: string | null
}

// Human-readable labels for the stable technique enum used across guides.
export const TECHNIQUE_LABELS: Record<string, string> = {
  cashback: '返现 Cashback',
  discounted_giftcard: '折扣礼品卡',
  education_store: '教育商店',
  credit_card_points: '信用卡积分',
  signup_bonus: '开户奖励',
  trade_in: '以旧换新',
  price_match: '价格匹配',
  coupon: '优惠券',
  sale_timing: '大促时机',
  membership: '会员权益',
  other: '其他',
}

export function techniqueLabel(technique: string): string {
  return TECHNIQUE_LABELS[technique] ?? technique
}

// The guides corpus lives at the repo root, one level above the frontend app.
const GUIDES_DIR = path.join(process.cwd(), '..', 'data', 'strategies', 'guides')

async function readGuideFile(file: string): Promise<Guide | null> {
  try {
    const raw = await fs.readFile(path.join(GUIDES_DIR, file), 'utf-8')
    return JSON.parse(raw) as Guide
  } catch {
    return null
  }
}

export async function getGuides(): Promise<Guide[]> {
  let files: string[]
  try {
    files = await fs.readdir(GUIDES_DIR)
  } catch {
    return [] // corpus not generated yet — render an empty state
  }
  const jsonFiles = files.filter((f) => f.endsWith('.json'))
  const guides = await Promise.all(jsonFiles.map(readGuideFile))
  return guides
    .filter((g): g is Guide => g !== null)
    .sort((a, b) => {
      const at = a.generated_at ?? ''
      const bt = b.generated_at ?? ''
      if (at !== bt) return bt.localeCompare(at) // newest first
      return a.goal.localeCompare(b.goal)
    })
}

export async function getGuide(id: string): Promise<Guide | null> {
  const guides = await getGuides()
  return guides.find((g) => g.id === id) ?? null
}

export async function getAllTechniques(): Promise<string[]> {
  const guides = await getGuides()
  const set = new Set<string>()
  for (const g of guides) for (const t of g.techniques) set.add(t)
  return [...set].sort()
}
