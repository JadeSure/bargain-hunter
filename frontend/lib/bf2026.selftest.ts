// Run: node --experimental-strip-types frontend/lib/bf2026.selftest.ts
// Inline fixtures only; does not read the repo data.
import assert from 'node:assert/strict'
// @ts-expect-error node needs the explicit .ts extension; tsc (bundler mode) rejects it
import * as d from './bf2026-derive.ts'
import type { Point, PrepStep, Watch } from './bf2026-derive'

let seq = 0
const mk = (o: Partial<Point>): Point => ({
  id: `ozb-${++seq}`,
  key: 'k',
  item: 'Thing',
  model: null,
  category: '数码电子',
  retailer: 'R',
  date: '2025-11-28',
  event: '黑五季',
  price: 100,
  was_price: null,
  was_suspect: false,
  conditions: '',
  votes: null,
  history_low: false,
  source: 'https://example.com',
  evidence: '',
  retrieved_at: '2026-10-31',
  note: '',
  file: 'ozbargain',
  ...o,
})

// outlier exclusion
{
  const contract = mk({ price: 13.86, was_price: 998.64, conditions: '合约', category: '数码电子' })
  const cheap = mk({ price: 3, was_price: 20 })
  const huge = mk({ price: 9, was_price: 100 })
  const fine = mk({ price: 60, was_price: 100 })
  const ds = d.discounts([contract, cheap, huge, fine])
  assert.deepEqual(ds.map((x) => x.point.id), [fine.id])
  const reasons = d.discountCandidates([contract, cheap, huge]).map((x) => d.excludeReason(x))
  assert.ok(reasons[0]?.startsWith('带条件'))
  assert.ok(reasons[1]?.includes('$5'))
  assert.ok(reasons[2]?.includes('90%'))
}

// Boxing Day January belongs to the previous season
{
  assert.equal(d.seasonYear(mk({ event: '节礼日', date: '2026-01-03' })), 2025)
  assert.equal(d.seasonYear(mk({ event: '节礼日', date: '2025-12-26' })), 2025)
  assert.equal(d.seasonYear(mk({ date: '2026-01-03' })), 2026)
}

// n < 5 -> no median
{
  const few = Array.from({ length: 4 }, () => mk({ price: 50, was_price: 100 }))
  assert.equal(d.categorySummary(d.discounts(few))[0].median, null)
  assert.equal(d.categorySummary(d.discounts([...few, mk({ price: 50, was_price: 100 })]))[0].median, 50)
  assert.deepEqual(d.categoryDepth(few), [])
  const other = Array.from({ length: 5 }, () => mk({ price: 50, was_price: 100, category: '其他' }))
  assert.deepEqual(d.categoryDepth(other), [])
  assert.equal(d.categoryDepth([...few, mk({ price: 50, was_price: 100 })])[0].median, 50)
}

// D1: votes on non-OzBargain rows are ignored
{
  assert.equal(d.votesOf(mk({ id: 'dm-9', votes: 500, file: 'dealmoon' })), null)
  assert.equal(d.votesOf(mk({ votes: 7 })), 7)
}

// forecast regression values (curated-only fixtures)
{
  const W = (key: string, kw: string): Watch => ({ key, item: key, category: '数码电子', who: '', verdict: '', why: '', kw })
  const cur = (key: string, price: number, o: Partial<Point> = {}) => mk({ key, price, file: 'curated', id: `cur-${++seq}`, date: '2025-11', ...o })
  const watch = [W('dyson-supersonic', 'dyson supersonic'), W('dyson-airwrap', 'dyson airwrap'), W('ninja-creami', 'ninja creami'), W('kitchenaid', 'kitchenaid'), W('dyson-v15', 'dyson v15')]
  const pts = [
    cur('dyson-supersonic', 350, { date: '2024-11' }),
    cur('dyson-supersonic', 299),
    cur('dyson-airwrap', 549, { date: '2024-11' }),
    cur('dyson-airwrap', 449),
    cur('dyson-airwrap', 294, { date: '2026-07', event: '其他促销', conditions: '套装' }),
    cur('ninja-creami', 180.6),
    cur('kitchenaid', 699),
  ]
  const [sup, air, nin, kit, v15] = d.forecast(watch, pts)
  assert.equal(sup.target, 299)
  assert.equal(sup.kw, 'dyson supersonic <=299')
  assert.equal(sup.range_text, '约 $299')
  assert.equal(air.target, 449)
  assert.equal(nin.target, 180.6)
  assert.equal(nin.kw, 'ninja creami <=181')
  assert.equal(kit.target, 699)
  assert.equal(v15.target, null)
  assert.equal(v15.kw, 'dyson v15')
  assert.equal(v15.range_text, '')
  // confidence: 2 season years -> 高, 1 -> 中, 0 -> 低; conditional points do not count
  assert.deepEqual([sup, air, nin, v15].map((f) => f.confidence), ['高', '高', '中', '低'])
  assert.equal(d.confidenceOf(3), '高')
  assert.deepEqual(sup.seasonMins.map((m) => [m.year, m.point.price]), [[2024, 350], [2025, 299]])
  assert.equal(sup.earliest, null)
  assert.equal(d.forecast([W('x', 'x')], [mk({ key: 'x', date: '2025-11-12' }), mk({ key: 'x', date: '2024-11-20' })])[0].earliest, '11-12')
  // seen26 ignores conditional 2026 points
  const f26 = d.forecast([W('y', 'y')], [mk({ key: 'y', date: '2026-09-01', price: 80 }), mk({ key: 'y', date: '2026-09-02', price: 20, conditions: '二手' })])[0]
  assert.equal(f26.seen26?.price, 80)
  assert.equal(f26.newest26?.date, '2026-09-01')
  assert.equal(d.forecast([W('z', 'z')], [mk({ key: 'z', date: '2026-09-02', price: 20, conditions: '二手' })])[0].seen26, null)
}

// broad key ignores non-curated points
{
  const watch: Watch[] = [{ key: 'ps5', item: 'PS5', category: '数码电子', who: '', verdict: '', why: '', kw: 'ps5', broad: true }]
  const pts = [mk({ key: 'ps5', price: 20, file: 'ozbargain' }), mk({ key: 'ps5', price: 629, file: 'curated', id: 'cur-ps5' })]
  const [broad] = d.forecast(watch, pts)
  assert.equal(broad.target, 629)
  assert.equal(broad.kw, 'ps5 <=629')
  assert.equal(broad.targetPoint?.id, 'cur-ps5')
  assert.equal(broad.confidence, '中')
}

// recurring: both years, no 其他, no conditions, 2025 min >= $50, trend word
{
  const r = (key: string, year: number, price: number, o: Partial<Point> = {}) => mk({ key, price, date: `${year}-11-20`, item: key, ...o })
  const pts = [
    r('both-same', 2024, 280), r('both-same', 2025, 289, { votes: 40, source: 'https://s/1' }),
    r('dropping', 2024, 400), r('dropping', 2025, 300),
    r('only25', 2025, 100),
    r('other', 2024, 100, { category: '其他' }), r('other', 2025, 100, { category: '其他' }),
    r('cond', 2024, 100, { conditions: '合约' }), r('cond', 2025, 100),
    r('cheap', 2024, 20), r('cheap', 2025, 49),
    r('boxing', 2024, 100, { event: '节礼日' }), r('boxing', 2025, 100),
  ]
  const out = d.recurring(pts, [])
  assert.deepEqual(out.map((x) => x.key).sort(), ['both-same', 'dropping'])
  const same = out.find((x) => x.key === 'both-same')!
  assert.deepEqual([same.p2024, same.p2025, same.trend, same.votes, same.source], [280, 289, '差不多', 40, 'https://s/1'])
  assert.equal(out.find((x) => x.key === 'dropping')?.trend, '降价中')
  // different size / model between the two yearly minimums is dropped; a colour suffix is kept
  const named = (key: string, y1: string, y2: string) => [r(key, 2024, 100, { item: y1 }), r(key, 2025, 90, { item: y2 })]
  assert.deepEqual(d.recurring(named('hb', 'Hugo Boss Bottled Eau De Toilette 100ml', 'Hugo Boss Bottled Eau De Toilette 200ml'), []), [])
  assert.deepEqual(d.recurring(named('ug', 'UGREEN Nexode 200W USB C Charger 6 Ports', 'UGREEN Nexode 200W USB C Charger 8 Ports'), []), [])
  const kept = d.recurring(named('mx', 'Logitech MX Master 3S Mouse', 'Logitech MX Master 3S Mouse Graphite'), [])
  assert.deepEqual(kept.map((x) => x.item), ['Logitech MX Master 3S Mouse Graphite'])
  // broad watch keys are excluded
  const broadWatch: Watch[] = [{ key: 'dropping', item: '', category: '', who: '', verdict: '', why: '', kw: '', broad: true }]
  assert.deepEqual(d.recurring(pts, broadWatch).map((x) => x.key), ['both-same'])
  // 5% boundary: 2025 = 0.95 x 2024 is not yet "降价中"
  assert.equal(d.recurring([r('edge', 2024, 200), r('edge', 2025, 190)], [])[0].trend, '差不多')
  assert.equal(d.recurring([r('edge', 2024, 200), r('edge', 2025, 189)], [])[0].trend, '降价中')
  assert.equal(d.recurring([r('edge', 2024, 200), r('edge', 2025, 210)], [])[0].trend, '差不多')
  assert.equal(d.recurring([r('edge', 2024, 200), r('edge', 2025, 211)], [])[0].trend, '涨价了')
}

// brands: >= 3 rows in each year, stopwords skipped, aliases mapped
{
  const rows = (item: string, y2024: number, y2025: number) => [
    ...Array.from({ length: y2024 }, () => mk({ item, date: '2024-11-20' })),
    ...Array.from({ length: y2025 }, () => mk({ item, date: '2025-11-20' })),
  ]
  const pts = [...rows('Dyson V8', 3, 5), ...rows('dyson Airwrap', 1, 1), ...rows('TP Link Router', 4, 3), ...rows('Oral B iO', 3, 3), ...rows('The Thing', 9, 9), ...rows('[Prime] X', 9, 9), ...rows('Lego Set', 2, 9)]
  const b = d.recurringBrands(pts)
  assert.deepEqual(b.map((x) => [x.name, x.n]), [['Dyson', 4], ['Oral-B', 3], ['TP-Link', 3]])
}

// timing shares add to 100 and split at Black Friday (2025-11-28, 2024-11-29)
{
  const at = (date: string) => mk({ date })
  const pts = [
    at('2025-11-07'), at('2025-11-17'), at('2025-11-17'), at('2025-11-20'), at('2025-11-28'),
    at('2024-11-19'), at('2024-11-29'), at('2024-12-03'), mk({ date: '2025-11-28', file: 'curated', id: 'cur-t' }), mk({ date: '2025-11' }),
  ]
  const t = d.timingShares(pts)
  assert.equal(t.total, 8)
  assert.deepEqual(t.counts, [3, 1, 1, 2, 1])
  assert.equal(t.pct.reduce((a, b) => a + b, 0), 100)
  assert.ok(Math.abs(t.beforeShare - 5 / 8) < 1e-9)
  for (const n of [1, 3, 7, 11]) {
    const many = Array.from({ length: n }, (_, i) => at(`2025-11-${String(10 + (i % 18)).padStart(2, '0')}`))
    assert.equal(d.timingShares(many).pct.reduce((a, b) => a + b, 0), 100)
  }
  assert.equal(d.timingShares([]).total, 0)
}

// this-week checklist window on a fixed "today"
{
  const step = (n: number, by: string): PrepStep => ({ step: n, phase: 'p', by, task: `t${n}`, detail: '', source: '' })
  const prep = [step(1, '2026-10-30'), step(2, '2026-11-01'), step(3, '2026-11-05'), step(4, '2026-11-08'), step(5, '2026-11-09'), step(6, '2026-11-20')]
  const w = d.weekPlan(prep, '2026-11-01')
  assert.deepEqual(w.now.map((s) => s.step), [2, 3, 4])
  assert.deepEqual(w.later.map((s) => s.step), [5, 6])
  const sparse = d.weekPlan(prep, '2026-11-06')
  assert.deepEqual(sparse.now.map((s) => s.step), [4, 5, 6])
  assert.deepEqual(sparse.later, [])
  assert.deepEqual(d.weekPlan(prep, '2026-12-01').now, [])
  assert.equal(d.addDays('2026-11-27', -10), '2026-11-17')
  assert.equal(d.weekday('2026-11-17'), '二')
}

// BF vs Boxing Day
{
  const bf = (date: string, o: Partial<Point> = {}) => mk({ date, price: 50, was_price: 100, ...o })
  const pts = [
    ...Array.from({ length: 6 }, () => bf('2025-11-28')),
    ...Array.from({ length: 2 }, () => mk({ event: '节礼日', date: '2025-12-26', price: 40, was_price: 100 })),
    mk({ event: '节礼日', date: '2026-01-03', price: 40, was_price: 100 }),
    bf('2025-11-28', { id: 'dm-1', file: 'dealmoon' }),
  ]
  const v = d.bfVsBoxing(pts)
  assert.equal(v.bfPerYear, 3)
  assert.equal(v.bdPerYear, 1.5)
  assert.equal(v.ratio, 2)
  assert.equal(v.bfMedian, 50)
  assert.equal(v.bdMedian, null)
}

// Black Friday dates
{
  assert.equal(new Date(d.blackFridayDate(2025)).toISOString().slice(0, 10), '2025-11-28')
  assert.equal(new Date(d.blackFridayDate(2024)).toISOString().slice(0, 10), '2024-11-29')
}

console.log('bf2026 selftest: ok')
