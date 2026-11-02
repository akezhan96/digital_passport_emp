export function evaluationDisplayState({ historical, stale, preview, dirty, hasSavedScore }) {
  if (historical) return 'historical'
  if (preview) return 'preview'
  if (stale && hasSavedScore) return 'stale'
  if (dirty) return 'unsaved'
  return hasSavedScore ? 'saved' : 'empty'
}

export function recruitmentActions(vacancy, latestRun) {
  const open = latestRun ? { kind: 'results', run: latestRun.id } : null
  const create = vacancy.status !== 'closed' ? { kind: latestRun ? 'rerun' : 'start', vacancy: vacancy.id } : null
  return { primary: open || create, secondary: open ? create : null }
}
