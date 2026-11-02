import test from 'node:test'
import assert from 'node:assert/strict'
import { dashboardDistribution } from '../src/dashboardCharts.js'

test('empty dashboard keeps every status visible with finite zero shares', () => {
  const result = dashboardDistribution({ total: 0 }, ['verified', 'draft'])
  assert.equal(result.total, 0)
  assert.deepEqual(result.rows.map(({ key, count, percent }) => ({ key, count, percent })), [
    { key: 'verified', count: 0, percent: 0 }, { key: 'draft', count: 0, percent: 0 }, { key: 'other', count: 0, percent: 0 },
  ])
})

test('archived and unrecognised statuses remain in the denominator and visible remainder', () => {
  const result = dashboardDistribution({ total: 20, verified: 10, draft: 2, in_review: 3, archived: 4, other: 1 }, ['verified', 'draft', 'in_review', 'archived'])
  assert.deepEqual(result.rows.map(row => row.count), [10, 2, 3, 4, 1])
  assert.deepEqual(result.rows.map(row => row.percent), [50, 10, 15, 20, 5])
  assert.deepEqual(result.rows.map(row => row.offset), [0, 50, 60, 75, 95])
  assert.equal(result.rows.reduce((sum, row) => sum + row.count, 0), result.total)
})

test('missing optional status counts do not silently omit the remaining records', () => {
  const result = dashboardDistribution({ total: 8, active: 3, draft: 2 }, ['active', 'draft', 'closed'])
  assert.equal(result.rows.at(-1).count, 3)
  assert.equal(result.rows.at(-1).percent, 37.5)
})

test('invalid counts cannot create NaN, negative slices or shares above one hundred', () => {
  for (const total of [undefined, -1, NaN, Infinity, '8']) {
    const result = dashboardDistribution({ total, active: 2 }, ['active'])
    assert.equal(result.total, 0)
    assert.ok(result.rows.every(row => row.count === 0 && row.percent === 0))
  }
  const result = dashboardDistribution({ total: 5, active: 10, draft: -1, closed: Infinity }, ['active', 'draft', 'closed'])
  assert.deepEqual(result.rows.map(row => row.count), [5, 0, 0, 0])
  assert.equal(result.rows.reduce((sum, row) => sum + row.percent, 0), 100)
})

test('fractional shares retain precision for a full donut and a single status fills it', () => {
  const result = dashboardDistribution({ total: 3, active: 1, draft: 1, closed: 1 }, ['active', 'draft', 'closed'])
  assert.ok(Math.abs(result.rows.reduce((sum, row) => sum + row.percent, 0) - 100) < 1e-10)
  const single = dashboardDistribution({ total: 100, active: 100 }, ['active', 'draft', 'closed'])
  assert.equal(single.rows[0].percent, 100)
  assert.ok(single.rows.slice(1).every(row => row.count === 0))
})
