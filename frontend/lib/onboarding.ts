// Mirrors the Python `Program` pydantic model (src/strategy_hunter/onboarding/models.py).
// Programs are produced by strategy_hunter and stored as JSON; this module reads
// them at build time so /start-here pages can be statically generated.
// Dynamic imports for `fs` and `path` keep this module loadable on the edge runtime
// (where those modules are unavailable); all program data reads return [] gracefully.

export interface ProgramStep {
  order: number
  action: string
  detail?: string | null
}

export interface Program {
  id: string
  name: string
  category: string
  one_liner: string
  benefit: string
  signup_bonus?: string | null
  needs_referral: boolean
  referral_note?: string | null
  how_to_join: ProgramStep[]
  prerequisites: string[]
  risks: string[]
  region: string
  recommended_for_newcomer: boolean
  priority: number
  est_value?: string | null
  official_url?: string | null
  sources: string[]
  valid_until?: string | null
  confidence?: number | null
  generated_at?: string | null
}

async function programsDir(): Promise<string> {
  const { join } = await import('path')
  const { default: process } = await import('process')
  return join(process.cwd(), '..', 'data', 'strategies', 'onboarding', 'programs')
}

async function readdir(dir: string): Promise<string[]> {
  try {
    const { promises: fs } = await import('fs')
    return await fs.readdir(dir)
  } catch {
    return []
  }
}

async function readProgramFile(filePath: string): Promise<Program | null> {
  try {
    const { promises: fs } = await import('fs')
    const raw = await fs.readFile(filePath, 'utf-8')
    return JSON.parse(raw) as Program
  } catch {
    return null
  }
}

export async function getPrograms(): Promise<Program[]> {
  const dir = await programsDir()
  const files = await readdir(dir)
  const jsonFiles = files.filter((f) => f.endsWith('.json'))
  const { join } = await import('path')
  const programs = await Promise.all(jsonFiles.map((f) => readProgramFile(join(dir, f))))
  return programs
    .filter((p): p is Program => p !== null)
    .sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority
      return a.name.localeCompare(b.name)
    })
}

export async function getProgram(id: string): Promise<Program | null> {
  const programs = await getPrograms()
  return programs.find((p) => p.id === id) ?? null
}

export async function getAllCategories(): Promise<string[]> {
  const programs = await getPrograms()
  const set = new Set<string>()
  for (const p of programs) set.add(p.category)
  return [...set].sort()
}

export async function getNewcomerChecklist(): Promise<Program[]> {
  const programs = await getPrograms()
  return programs.filter((p) => p.recommended_for_newcomer)
}
