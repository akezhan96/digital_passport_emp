const count = value => Number.isSafeInteger(value) && value > 0 ? value : 0

/** Keep shares finite and preserve uncategorised records in an explicit remainder. */
export function dashboardDistribution(snapshot = {}, keys = []) {
  const total = count(snapshot.total)
  let remaining = total
  let offset = 0
  const rows = [...keys, 'other'].map(key => {
    const value = key === 'other' ? remaining : Math.min(count(snapshot[key]), remaining)
    const percent = total ? value / total * 100 : 0
    const row = { key, count: value, percent, offset }
    remaining -= value
    offset += percent
    return row
  })
  return { total, rows }
}
