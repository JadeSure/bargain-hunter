// Mirrors the Python `Guide` pydantic model (src/strategy_hunter/models.py).
// Guides are produced by strategy_hunter and stored as JSON; this module reads
// them at build time so /guides pages can be statically generated.
// Dynamic imports for `fs` and `path` keep this module loadable on the edge runtime
// (where those modules are unavailable); all guide data reads return [] gracefully.

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

export const TECHNIQUE_LABELS: Record<string, string> = {
  cashback: 'Cashback',
  discounted_giftcard: 'Discounted Gift Cards',
  education_store: 'Education Store',
  credit_card_points: 'Credit Card Points',
  signup_bonus: 'Sign-up Bonus',
  trade_in: 'Trade-in',
  price_match: 'Price Match',
  coupon: 'Coupon',
  sale_timing: 'Sale Timing',
  membership: 'Membership',
  other: 'Other',
}

export function techniqueLabel(technique: string): string {
  return TECHNIQUE_LABELS[technique] ?? technique
}

async function guidesDir(): Promise<string> {
  const { join } = await import('path')
  const { default: process } = await import('process')
  return join(process.cwd(), '..', 'data', 'strategies', 'guides')
}

async function readdir(dir: string): Promise<string[]> {
  try {
    const { promises: fs } = await import('fs')
    return await fs.readdir(dir)
  } catch {
    return []
  }
}

async function readGuideFile(filePath: string): Promise<Guide | null> {
  try {
    const { promises: fs } = await import('fs')
    const raw = await fs.readFile(filePath, 'utf-8')
    return JSON.parse(raw) as Guide
  } catch {
    return null
  }
}

export async function getGuides(): Promise<Guide[]> {
  const dir = await guidesDir()
  const files = await readdir(dir)
  const jsonFiles = files.filter((f) => f.endsWith('.json'))
  const { join } = await import('path')
  const guides = await Promise.all(jsonFiles.map((f) => readGuideFile(join(dir, f))))
  return guides
    .filter((g): g is Guide => g !== null)
    .sort((a, b) => {
      const at = a.generated_at ?? ''
      const bt = b.generated_at ?? ''
      if (at !== bt) return bt.localeCompare(at)
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
