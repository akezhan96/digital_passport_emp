// The API accepts at most two decimal places. Keep hundredths as integers and
// use exact HALF_UP division, matching Python Decimal rather than float ties.
export function pointsToHundredths(value) {
  if (value === null || value === undefined || String(value).trim() === '') return null
  const text = String(value).trim()
  if (text.length > 80) return null
  const match = text.match(/^\+?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/)
  if (!match) return null
  const fraction = match[2] ?? match[3] ?? ''
  const exponent = Number(match[4] || 0)
  if (!Number.isInteger(exponent) || Math.abs(exponent) > 20) return null
  const coefficient = BigInt((match[1] || '0') + fraction)
  const scale = fraction.length - exponent
  if (scale <= 2) return coefficient * 10n ** BigInt(2 - scale)
  const divisor = 10n ** BigInt(scale - 2)
  return coefficient % divisor === 0n ? coefficient / divisor : null
}

export function candidatePointsPreview(criteria, values, technicalProfile, baseSummary = {}) {
  const applicable = criteria.filter(c => c.enabled && (technicalProfile || c.block !== 'technical'))
  let maximum = 0n, earned = 0n, filled = 0, invalid = 0
  for (const criterion of applicable) {
    const max = pointsToHundredths(criterion.max_points)
    if (max === null || max <= 0n) { invalid += 1; continue }
    maximum += max
    const value = values[criterion.position]
    if (value === undefined || value === null || String(value).trim() === '') continue
    const points = pointsToHundredths(value)
    if (points === null || points > max) { invalid += 1; continue }
    earned += points
    filled += 1
  }
  const hasScore = filled > 0 && invalid === 0
  const percentHundredths = hasScore && maximum > 0n
    ? (earned * 10000n * 2n + maximum) / (maximum * 2n) : null
  return { ...baseSummary, technical_profile: technicalProfile,
    earned_points: hasScore ? Number(earned) / 100 : null,
    max_points: Number(maximum) / 100,
    percent: percentHundredths === null ? null : Number(percentHundredths) / 100,
    filled_count: filled, applicable_count: applicable.length,
    missing_count: applicable.length - filled, invalid_count: invalid,
    complete: applicable.length > 0 && filled === applicable.length && invalid === 0 }
}
