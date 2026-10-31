// Run: node --experimental-strip-types frontend/lib/bf2026.selftest.ts
// Inline fixtures only; does not read the repo data.
import assert from 'node:assert/strict'
// @ts-expect-error node needs the explicit .ts extension; tsc (bundler mode) rejects it
import * as d from './bf2026-derive.ts'
import type { Point, Watch } from './bf2026-derive'

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

// same shopping year: 2025 BF is never compared with 2018 Boxing Day or 2026-07
{
  const pts = [
    mk({ price: 69, item: 'Game 7' }),
    mk({ price: 15, event: '节礼日', date: '2018-12-24', item: 'Game 7' }),
    mk({ price: 10, event: '其他促销', date: '2026-07-10', item: 'Game 7' }),
  ]
  assert.equal(d.comparePairs(pts).length, 0)
  const ok = [...pts, mk({ price: 80, event: '平日', date: '2025-07-02', item: 'Game 7' })]
  const pairs = d.comparePairs(ok)
  assert.equal(pairs.length, 1)
  assert.equal(pairs[0].other.price, 80)
  assert.equal(pairs[0].beaten, false)
  assert.equal(d.boxingPairs(pts).length, 0)
}

// outlier exclusion
{
  const contract = mk({ price: 13.86, was_price: 998.64, conditions: '合约', category: '数码电子' })
  const cheap = mk({ price: 3, was_price: 20 })
  const huge = mk({ price: 9, was_price: 100 })
  const fine = mk({ price: 60, was_price: 100 })
  const ds = d.discounts([contract, cheap, huge, fine])
  assert.deepEqual(ds.map((x) => x.point.id), [fine.id])
  const ex = d.excludedDiscounts([contract, cheap, huge, fine])
  assert.equal(ex.length, 3)
  assert.ok(ex.find((x) => x.point.id === contract.id)?.reason.startsWith('带条件'))
  assert.ok(ex.find((x) => x.point.id === cheap.id)?.reason.includes('$5'))
  assert.ok(ex.find((x) => x.point.id === huge.id)?.reason.includes('90%'))
}

// Boxing Day January belongs to the previous season
{
  const jan = mk({ event: '节礼日', date: '2026-01-03' })
  const dec = mk({ event: '节礼日', date: '2025-12-26' })
  assert.equal(d.seasonYear(jan), 2025)
  assert.equal(d.seasonYear(dec), 2025)
  assert.equal(d.seasonYear(mk({ date: '2026-01-03' })), 2026)
  const pts = [mk({ price: 300 }), mk({ price: 250, event: '节礼日', date: '2026-01-03' })]
  const bp = d.boxingPairs(pts)
  assert.equal(bp.length, 1)
  assert.equal(bp[0].boxing_cheaper, true)
  assert.equal(bp[0].saving_pct, 17)
}

// ranking: ozb votes first, then discount
{
  const a = mk({ price: 10, was_price: 100, votes: 5 })
  const b = mk({ price: 50, was_price: 100, votes: 80 })
  const c = mk({ id: 'dm-1', price: 20, was_price: 100, file: 'dealmoon', event: '黑五季' })
  const e = mk({ id: 'cur-1', price: 80, was_price: 100, file: 'curated' })
  const order = d.rankDeals(d.discounts([c, e, a, b])).map((x) => x.point.id)
  assert.deepEqual(order, [b.id, a.id, 'dm-1', 'cur-1'])
}

// n < 5 -> no median
{
  const few = Array.from({ length: 4 }, () => mk({ price: 50, was_price: 100 }))
  const s4 = d.categorySummary(d.discounts(few))
  assert.equal(s4[0].n, 4)
  assert.equal(s4[0].median, null)
  const s5 = d.categorySummary(d.discounts([...few, mk({ price: 50, was_price: 100 })]))
  assert.equal(s5[0].median, 50)
  assert.equal(d.overallMedian(d.discounts(few)), null)
}

// D1: votes on non-OzBargain rows are ignored
{
  const dm = mk({ id: 'dm-9', votes: 500, file: 'dealmoon' })
  const oz = mk({ votes: 7 })
  assert.equal(d.votesOf(dm), null)
  assert.equal(d.votesOf(oz), 7)
  const f = { cats: ['数码电子'], year: null, file: null, minVotes: 20 }
  const side = (p: Point) => ({ file: p.file, votes: d.votesOf(p) })
  assert.equal(d.pairPasses({ category: '数码电子', year: 2025, sides: [side(dm)] }, f), true)
  assert.equal(d.pairPasses({ category: '数码电子', year: 2025, sides: [side(oz)] }, f), false)
  const ranked = d.rankDeals(d.discounts([mk({ id: 'dm-2', votes: 999, file: 'dealmoon', price: 90, was_price: 100 }), mk({ price: 50, was_price: 100, votes: 3 })]))
  assert.equal(ranked[0].point.votes, 3)
}

// D2: broad key ignores non-curated points
{
  const watch: Watch[] = [
    { key: 'ps5', item: 'PS5', category: '数码电子', who: '', verdict: '', why: '', kw: 'ps5', broad: true },
    { key: 'plain', item: 'Plain', category: '数码电子', who: '', verdict: '', why: '', kw: 'plain' },
  ]
  const pts = [
    mk({ key: 'ps5', price: 20, file: 'ozbargain' }),
    mk({ key: 'ps5', price: 629, file: 'curated', id: 'cur-ps5' }),
    mk({ key: 'plain', price: 20, file: 'ozbargain' }),
    mk({ key: 'plain', price: 629, file: 'curated', id: 'cur-plain' }),
  ]
  const [broad, plain] = d.forecast(watch, pts)
  assert.equal(broad.target, 629)
  assert.equal(broad.kw, 'ps5 <=629')
  assert.equal(broad.targetPoint?.id, 'cur-ps5')
  assert.equal(plain.target, 20)
}

// D3: comparable items
{
  assert.equal(d.comparableItems('Call of Duty: Black Ops 6', 'Call of Duty: Black Ops 7'), false)
  assert.equal(d.comparableItems('Dyson Supersonic Hair Dryer', 'Dyson Supersonic Hair Dryer (Nickel)'), true)
  assert.equal(d.comparableItems('Dyson Supersonic', 'Garmin Forerunner'), false)
  const pts = [
    mk({ key: 'cod', item: 'Black Ops 7', price: 69 }),
    mk({ key: 'cod', item: 'Black Ops 6', price: 40, event: '平日', date: '2026-02-01' }),
  ]
  const pairs = d.comparePairs(pts)
  assert.equal(pairs.length, 1)
  assert.equal(pairs[0].comparable, false)
  assert.equal(d.suspectCount(pairs), 1)
}

// curated-only forecast regression values
{
  const watch: Watch[] = [{ key: 'kindle-pw', item: 'Kindle', category: '数码电子', who: '', verdict: '', why: '', kw: 'kindle paperwhite' }]
  const pts = [mk({ key: 'kindle-pw', price: 229, file: 'curated', id: 'cur-k' }), mk({ key: 'kindle-pw', price: 180, conditions: '二手' })]
  assert.equal(d.forecast(watch, pts)[0].target, 229)
}

// timing: Black Friday dates
{
  assert.equal(new Date(d.blackFridayDate(2025)).toISOString().slice(0, 10), '2025-11-28')
  assert.equal(new Date(d.blackFridayDate(2024)).toISOString().slice(0, 10), '2024-11-29')
  const t = d.timing([mk({ date: '2025-11-28', votes: 60 }), mk({ date: '2025-11-27' })], '黑五季', -21, 5)
  assert.equal(t[0].days.find((x) => x.off === 0)?.hot, 1)
  assert.equal(t[0].days.find((x) => x.off === -1)?.n, 1)
}

console.log('bf2026 selftest: ok')
