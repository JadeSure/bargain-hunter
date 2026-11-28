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

// median discount per timing bucket: outliers out, before/after groups combined
{
  const row = (date: string, price: number, o: Partial<Point> = {}) => mk({ date, price, was_price: 100, ...o })
  const pts = [
    row('2025-11-10', 60), row('2025-11-10', 80), row('2025-11-18', 70), row('2025-11-20', 50),
    row('2025-11-28', 40), row('2025-11-30', 55), row('2025-11-30', 20, { conditions: '合约' }),
    row('2025-11-30', 10, { was_suspect: true }), row('2025-11-30', 50, { was_price: null }),
    row('2025-11-30', 50, { id: 'cur-x', file: 'curated' }), row('2025-12-05', 3),
  ]
  const t = d.timingDepth(pts)
  assert.equal(t.total, 6)
  assert.deepEqual(t.buckets.map((b) => [b.n, b.median]), [[2, 30], [1, 30], [1, 50], [1, 60], [1, 45]])
  assert.deepEqual([t.before.n, t.before.median], [4, 35])
  assert.deepEqual([t.after.n, t.after.median], [2, 53])
  assert.deepEqual(d.timingDepth([]).before, { n: 0, median: null })
}

// early vs BF day: same-item pairs (2% band, word sets, leading tag, ignored rows) and deep deals
{
  const bef = '2025-11-20'
  const aft = '2025-11-28'
  const r = (key: string, date: string, price: number, o: Partial<Point> = {}) => mk({ key, date, price, item: 'Widget Pro', ...o })
  const pair = (key: string, before: number, after: number, o: Partial<Point> = {}) => [r(key, bef, before, o), r(key, aft, after, o)]
  const pts = [
    ...pair('cheap', 100, 97), ...pair('edge-a', 100, 98), ...pair('edge-b', 98, 100), ...pair('rev', 90, 100),
    r('words', bef, 100, { item: 'Ring Battery Video Doorbell' }), r('words', aft, 50, { item: 'Ring Battery Video Doorbell Plus + Ring Chime' }),
    r('plat', bef, 100, { evidence: '[PS5] game' }), r('plat', aft, 50, { evidence: '[XSX] game' }),
    ...pair('cond', 100, 50, { conditions: '合约' }), ...pair('misc', 100, 50, { category: '其他' }),
    r('tag-same', bef, 100, { evidence: '[PS5] game, deal A' }), r('tag-same', aft, 50, { evidence: '[PS5] game, deal B' }),
    r('xyear', '2024-11-20', 100), r('xyear', aft, 50),
    r('min', bef, 90), r('min', '2025-11-21', 150), r('min', aft, 100),
    r('only-before', bef, 100),
  ]
  const e = d.earlyVsBfDay(pts)
  assert.deepEqual([e.pairs, e.afterCheaper, e.same, e.beforeCheaper], [6, 2, 2, 2])

  const deep = [
    r('d1', bef, 40, { was_price: 100 }), r('d1', aft, 80, { was_price: 100 }),
    r('d2', bef, 50, { was_price: 100 }), r('d2', aft, 30, { was_price: 100, conditions: '合约' }),
    r('d3', aft, 49, { was_price: 100 }), r('d4', bef, 51, { was_price: 100 }), r('d5', bef, 4, { was_price: 100 }),
  ]
  const f = d.earlyVsBfDay(deep)
  assert.deepEqual([f.deepBefore, f.deepAfter], [2, 1])
  assert.deepEqual(d.earlyVsBfDay([]), { pairs: 0, afterCheaper: 0, same: 0, beforeCheaper: 0, deepBefore: 0, deepAfter: 0 })
}

// gift depth: best discount, no-data keys, broad keys use curated points only, band edges, sort
{
  const w = (key: string, who: string, broad = false): Watch => ({ key, item: `item-${key}`, category: '礼品', who, verdict: '黑五入手', why: '', kw: '', broad })
  const bf = (key: string, price: number, was: number, o: Partial<Point> = {}) => mk({ key, price, was_price: was, item: `p-${key}`, ...o })
  const pts = [
    bf('a', 70, 100, { date: '2024-11-29' }), bf('a', 50, 100, { date: '2025-11-28' }),
    bf('t', 60, 100, { date: '2024-11-29' }), bf('t', 60, 100, { date: '2025-11-28' }),
    bf('b', 20, 100), bf('c', 80, 100, { file: 'curated', id: 'cur-c' }), bf('c', 20, 100),
    bf('e1', 49.99, 100), bf('e2', 50, 100), bf('e3', 299.99, 1000), bf('e4', 300, 1000),
    bf('lo', 10, 12),
  ]
  const watch = [w('a', '送国内亲友'), w('t', 'Secret Santa'), w('b', '自用'), w('c', '送伴侣家人', true), w('none', '送国内亲友')]
  const g = d.giftDepth(pts, watch, [{ key: 'e1', who: '送伴侣家人' }, { key: 'e2', who: '送伴侣家人' }, { key: 'e3', who: '送伴侣家人' }, { key: 'e4', who: '送伴侣家人' }, { key: 'lo', who: '送伴侣家人' }])
  assert.deepEqual(g.bands.map((b) => b.items.map((i) => i.key)), [['e1', 'lo'], ['e3', 'a', 'e2', 't', 'c'], ['e4']])
  const item = (k: string) => g.bands.flatMap((b) => b.items).find((i) => i.key === k)
  assert.deepEqual([item('a')?.pct, item('a')?.year, item('a')?.price, item('a')?.name], [50, 2025, 50, 'item-a'])
  assert.equal(item('t')?.year, 2025)
  assert.deepEqual([item('c')?.pct, item('e1')?.name], [20, 'p-e1'])
  assert.deepEqual(g.noData, ['item-none'])
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

// ── P0 acceptance (docs/BF2026_UI_PRD.md §6) ────────────────

const pack = (u: string) => u

// 1. Same shopping year only: a 2025 Black Friday price is never compared with a 2018
// Boxing Day price, nor with a July 2026 one. Shopping year Y = Y-06-01 .. (Y+1)-05-31.
{
  assert.equal(d.shoppingYear(mk({ date: '2025-11-28' })), 2025)
  assert.equal(d.shoppingYear(mk({ date: '2026-01-03', event: '节礼日' })), 2025)
  assert.equal(d.shoppingYear(mk({ date: '2026-05-31', event: '其他促销' })), 2025)
  assert.equal(d.shoppingYear(mk({ date: '2026-06-01', event: 'EOFY' })), 2026)
  assert.equal(d.shoppingYear(mk({ date: '2026-07-15', event: 'Prime Day' })), 2026)

  const pts = [
    mk({ key: 'tv', date: '2025-11-28', price: 900 }),
    mk({ key: 'tv', date: '2018-12-26', event: '节礼日', price: 150 }),
    mk({ key: 'tv', date: '2026-07-15', event: 'Prime Day', price: 100 }),
    mk({ key: 'tv', date: '2026-01-05', event: '节礼日', price: 800 }),
  ]
  const rows = d.seasonRows(pts, pack)
  // 2025: BF 900 vs the Jan-2026 Boxing Day 800 — the 2018 and the 2026-07 rows are other years.
  const y2025 = rows.filter((r) => r[1] === 2025)
  assert.equal(y2025.length, 1)
  assert.equal(y2025[0][4], 900)
  assert.equal(y2025[0][5], 800)
  assert.equal(y2025[0][6], '节礼日')
  // 2018 and 2026 have only one side each, so they make no pair at all.
  assert.deepEqual(rows.map((r) => r[1]).sort(), [2025])

  const f = d.defaultFilter()
  const cmp = d.compareShoppingYear(rows, { ...f, minVotes: 0 })
  assert.equal(cmp.pairs, 1)
  assert.equal(cmp.otherCheaper, 1)
  assert.equal(cmp.bfCheaper, 0)

  // A gap under 2% counts as "about the same".
  const near = d.seasonRows(
    [mk({ key: 'x', date: '2025-11-28', price: 100 }), mk({ key: 'x', date: '2025-12-26', event: '节礼日', price: 99 })],
    pack,
  )
  const nearCmp = d.compareShoppingYear(near, { ...f, minVotes: 0 })
  assert.equal(nearCmp.same, 1)
}

// 2. Outlier exclusion feeds both the board rows and the "已排除 n 条" list.
{
  const contract = mk({ price: 13.86, was_price: 998.64, conditions: '合约', item: 'iPhone 16e 128GB' })
  const cheap = mk({ price: 3, was_price: 20 })
  const fine = mk({ price: 60, was_price: 100, votes: 30 })
  const rows = d.boardRows([contract, cheap, fine], ['ozbargain'], pack)
  assert.equal(rows.length, 1)
  assert.equal(rows[0][6], 60)
  const ex = d.excludedRows([contract, cheap, fine], pack)
  assert.equal(ex.length, 2)
  assert.ok(ex[0][5].startsWith('带条件'))
  assert.equal(ex[0][2], 99)
  assert.ok(ex[1][5].includes('$5'))
}

// 3. A January Boxing Day price belongs to the previous season, in the board rows too.
{
  const jan = d.boardRows([mk({ event: '节礼日', date: '2026-01-03', price: 50, was_price: 100 })], ['ozbargain'], pack)
  assert.equal(jan[0][2], 2025)
  assert.equal(jan[0][1], d.BD_EVENT)
}

// 4. Board order: rows with votes first, by votes; rows without votes after, by discount.
{
  const row = (votes: number, pct: number): d.BoardRow => [0, d.BF_EVENT, 2025, 0, votes, pct, 100, 200, 'i', 'r', 'u']
  const sorted = d.boardSort([row(d.NO_VOTES, 80), row(5, 10), row(40, 20), row(d.NO_VOTES, 90), row(12, 70)])
  assert.deepEqual(sorted.map((r) => [r[4], r[5]]), [
    [40, 20],
    [12, 70],
    [5, 10],
    [d.NO_VOTES, 90],
    [d.NO_VOTES, 80],
  ])
}

// 5. Under MIN_SAMPLE rows a category reports no median, and the vote threshold only
// touches OzBargain rows.
{
  const f = { ...d.defaultFilter(), minVotes: 0, other: true }
  const four = Array.from({ length: 4 }, () => mk({ price: 50, was_price: 100, votes: 30 }))
  const rows4 = d.boardRows(four, ['ozbargain'], pack)
  assert.equal(d.depthOf(rows4, f)[0].median, null)
  assert.equal(d.depthOf(rows4, f)[0].n, 4)
  const rows5 = d.boardRows([...four, mk({ price: 50, was_price: 100, votes: 30 })], ['ozbargain'], pack)
  assert.equal(d.depthOf(rows5, f)[0].median, 50)

  // votes >= 20 keeps the OzBargain row and never drops a source that has no votes at all.
  const ozbLow = mk({ price: 50, was_price: 100, votes: 3 })
  const dealmoon = mk({ id: 'dm-1', file: 'dealmoon', price: 50, was_price: 100, votes: 500 })
  const mixed = d.boardRows([ozbLow, dealmoon], ['ozbargain', 'dealmoon'], pack)
  assert.equal(d.filterRows(mixed, { ...f, minVotes: 0 }).length, 2)
  const gated = d.filterRows(mixed, { ...f, minVotes: d.DEFAULT_MIN_VOTES })
  assert.equal(gated.length, 1)
  assert.equal(gated[0][4], d.NO_VOTES)
  assert.ok(d.passesVotes(d.NO_VOTES, 50))
  assert.ok(!d.passesVotes(19, 20))
  assert.ok(d.passesVotes(20, 20))
}

// 其他 is out unless asked for; an empty category pick means every category.
{
  const f = d.defaultFilter()
  assert.ok(!d.keepsCat(d.OTHER_CAT, f))
  assert.ok(d.keepsCat(d.OTHER_CAT, { ...f, other: true }))
  assert.ok(d.keepsCat(0, f))
  assert.ok(!d.keepsCat(1, { ...f, cats: [0] }))
}

// Deal counts average over the seasons the filter leaves in, and name them.
{
  const cells: d.CountCell[] = [
    [0, d.BF_EVENT, 2024, 0, 10, 4, 1],
    [0, d.BF_EVENT, 2025, 0, 20, 6, 2],
    [0, d.BD_EVENT, 2024, 0, 5, 2, 0],
    [0, d.BD_EVENT, 2025, 0, 5, 3, 0],
  ]
  const f = { ...d.defaultFilter(), minVotes: 0 }
  const all = d.countsOf(cells, f)
  assert.deepEqual(all.years, [2024, 2025])
  assert.equal(all.bfPerYear, 15)
  assert.equal(all.bdPerYear, 5)
  assert.equal(all.ratio, 3)
  const y2025 = d.countsOf(cells, { ...f, year: 2025 })
  assert.deepEqual(y2025.years, [2025])
  assert.equal(y2025.bfPerYear, 20)
  // the vote threshold picks the matching pre-counted column
  assert.equal(d.countsOf(cells, { ...f, minVotes: 20 }).bfPerYear, 5)
  assert.equal(d.countsOf(cells, { ...f, minVotes: 50 }).bfPerYear, 1.5)
}

// URL round-trip: the default is written as a clean URL and read back unchanged. A missing
// `votes` key must keep the default threshold, not parse as the valid value 0.
{
  const files = ['curated', 'dealmoon', 'ozbargain']
  const dflt = d.defaultFilter()
  assert.equal(d.writeFilter(dflt, files), '')
  assert.deepEqual(d.readFilter('', files), dflt)
  assert.equal(d.readFilter('', files).minVotes, d.DEFAULT_MIN_VOTES)
  assert.equal(d.readFilter('?cat=home', files).minVotes, d.DEFAULT_MIN_VOTES)
  assert.equal(d.readFilter('?votes=0', files).minVotes, 0)
  assert.equal(d.readFilter('?votes=7', files).minVotes, d.DEFAULT_MIN_VOTES)

  const picked: d.Filter = { cats: [0, 1], year: 2025, file: 2, minVotes: 50, other: true }
  const qs = d.writeFilter(picked, files)
  assert.equal(qs, '?cat=tech%2Chome&year=2025&src=ozbargain&votes=50&other=1')
  assert.deepEqual(d.readFilter(qs, files), picked)

  // junk falls back to the default rather than throwing
  assert.deepEqual(d.readFilter('?cat=nope&year=abc&src=nope&votes=nope', files), dflt)
}

console.log('bf2026 selftest: ok')
