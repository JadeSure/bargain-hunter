// Hidden Black Friday 2026 page data. Reads ../data/bf2026 at build time (see lib/guides.ts
// for why fs/path are imported dynamically). Pure derivations live in bf2026-derive.ts so the
// client bundle never pulls in the fs loader.
import type { Bf2026Data, CalendarEvent, Fact, Gift, ItemImage, PrepStep, Promo, Point, Rule, Signal, Watch } from './bf2026-derive'

export * from './bf2026-derive'

// Only a missing file means "no data"; parse errors and non-arrays are reported in `errors`.
async function readJson<T>(path: string, errors: string[]): Promise<T[]> {
  const { promises: fs } = await import('fs')
  const { basename } = await import('path')
  let raw: string
  try {
    raw = await fs.readFile(path, 'utf-8')
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== 'ENOENT') errors.push(`${basename(path)}: ${String(e)}`)
    return []
  }
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows)) throw new Error('not a JSON array')
    return rows as T[]
  } catch (e) {
    errors.push(`${basename(path)}: ${e instanceof Error ? e.message : String(e)}`)
    return []
  }
}

// Same contract as readJson, for a file holding one object (images.json: item key -> picture).
async function readMap<T>(path: string, errors: string[]): Promise<Record<string, T>> {
  const { promises: fs } = await import('fs')
  const { basename } = await import('path')
  let raw: string
  try {
    raw = await fs.readFile(path, 'utf-8')
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== 'ENOENT') errors.push(`${basename(path)}: ${String(e)}`)
    return {}
  }
  try {
    const map = JSON.parse(raw)
    if (map === null || typeof map !== 'object' || Array.isArray(map)) throw new Error('not a JSON object')
    return map as Record<string, T>
  } catch (e) {
    errors.push(`${basename(path)}: ${e instanceof Error ? e.message : String(e)}`)
    return {}
  }
}

// A bad points/promos file is skipped and reported in `errors` instead of failing the build.
async function readFolder<T>(dir: string, errors: string[]): Promise<(T & { file: string })[]> {
  const { promises: fs } = await import('fs')
  const { join } = await import('path')
  let names: string[]
  try {
    names = (await fs.readdir(dir)).filter((f) => f.endsWith('.json')).sort()
  } catch {
    return []
  }
  const lists = await Promise.all(
    names.map(async (n) => {
      const rows = await readJson<T>(join(dir, n), errors)
      return rows.map((r) => ({ ...r, file: n.replace(/\.json$/, '') }))
    }),
  )
  return lists.flat()
}

export async function loadBf2026(): Promise<Bf2026Data> {
  const { join } = await import('path')
  const { default: process } = await import('process')
  const root = join(process.cwd(), '..', 'data', 'bf2026')
  const errors: string[] = []
  const [points, promos, watch, calendar, prep, rules, facts, signals, images, gifts] = await Promise.all([
    readFolder<Omit<Point, 'file'>>(join(root, 'points'), errors),
    readFolder<Omit<Promo, 'file'>>(join(root, 'promos'), errors),
    readJson<Watch>(join(root, 'watch.json'), errors),
    readJson<CalendarEvent>(join(root, 'calendar.json'), errors),
    readJson<PrepStep>(join(root, 'prep.json'), errors),
    readJson<Rule>(join(root, 'rules.json'), errors),
    readJson<Fact>(join(root, 'facts.json'), errors),
    readJson<Signal>(join(root, 'signals.json'), errors),
    readMap<ItemImage>(join(root, 'images.json'), errors),
    readJson<Gift>(join(root, 'gifts.json'), errors),
  ])
  return { points, promos, watch, calendar, prep, rules, facts, signals, images, gifts, errors }
}
