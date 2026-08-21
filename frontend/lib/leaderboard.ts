// Reads the rates & prices leaderboard artifact (data/leaderboard.json, written
// by src/bargain_hunter/leaderboard.py) at build time. Dynamic imports for
// fs/path keep this module loadable on the edge runtime, mirroring lib/guides.ts
// and lib/deals.ts -- reads return an empty board rather than throwing.

export interface BankProduct {
  brand: string
  name: string
  category: string
  best_rate: number | null
  bonus_points: number | null
  url: string
}

export interface LlmModel {
  id: string
  name: string
  prompt_usd_per_token: number
  completion_usd_per_token: number
  url: string
}

export interface LeaderboardData {
  bankProducts: BankProduct[]
  bankUpdatedAt: string | null
  llmModels: LlmModel[]
  llmUpdatedAt: string | null
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function readArtifact(): Promise<any> {
  try {
    const { promises: fs } = await import('fs')
    const { join } = await import('path')
    const { default: process } = await import('process')
    const path = join(process.cwd(), '..', 'data', 'leaderboard.json')
    return JSON.parse(await fs.readFile(path, 'utf-8'))
  } catch {
    return {}
  }
}

export async function getLeaderboard(): Promise<LeaderboardData> {
  const data = await readArtifact()
  return {
    bankProducts: Object.values(data.bank_products ?? {}),
    bankUpdatedAt: data.bank_products_updated_at ?? null,
    llmModels: data.llm_models ?? [],
    llmUpdatedAt: data.llm_models_updated_at ?? null,
  }
}

const SAVINGS_CATEGORIES = new Set(['TRANS_AND_SAVINGS_ACCOUNTS', 'TERM_DEPOSITS'])

export function topSavingsRates(products: BankProduct[], limit = 20): BankProduct[] {
  return products
    .filter((p) => SAVINGS_CATEGORIES.has(p.category) && p.best_rate !== null)
    .sort((a, b) => (b.best_rate ?? 0) - (a.best_rate ?? 0))
    .slice(0, limit)
}

export function topSignupBonuses(products: BankProduct[], limit = 20): BankProduct[] {
  return products
    .filter((p) => p.category === 'CRED_AND_CHRG_CARDS' && p.bonus_points !== null)
    .sort((a, b) => (b.bonus_points ?? 0) - (a.bonus_points ?? 0))
    .slice(0, limit)
}

export function cheapestModels(
  models: LlmModel[],
  limit = 20,
): { free: LlmModel[]; paid: LlmModel[] } {
  const free = models.filter(
    (m) => m.prompt_usd_per_token === 0 && m.completion_usd_per_token === 0,
  )
  const paid = models
    .filter((m) => m.prompt_usd_per_token > 0)
    .sort((a, b) => a.prompt_usd_per_token - b.prompt_usd_per_token)
    .slice(0, limit)
  return { free, paid }
}

const CATEGORY_LABELS: Record<string, string> = {
  TRANS_AND_SAVINGS_ACCOUNTS: 'Savings account',
  TERM_DEPOSITS: 'Term deposit',
  CRED_AND_CHRG_CARDS: 'Credit card',
}
export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category
}

export function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`
}

export function formatUsdPerMillion(usdPerToken: number): string {
  const perMillion = usdPerToken * 1e6
  return `US$${perMillion < 1 ? perMillion.toFixed(3) : perMillion.toFixed(2)}`
}

// Small self-contained relative-time formatter (not lib/deals.ts's formatAge --
// that file is under active concurrent development elsewhere in this pass).
export function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const ms = Date.now() - Date.parse(iso)
  if (Number.isNaN(ms)) return 'unknown'
  const hours = ms / 3_600_000
  if (hours < 1) return `${Math.max(1, Math.round(ms / 60_000))}m ago`
  if (hours < 48) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}
