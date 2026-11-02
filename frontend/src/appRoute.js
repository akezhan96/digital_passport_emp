// Keep the full route as the navigation identity: opening another record on
// the same screen must also respect unsaved changes and browser Back/Forward.
export function resolveAppRoute(hash, pages) {
  const route = String(hash || '').replace(/^#\/?/, '')
  const page = route.split('?')[0]
  return Object.hasOwn(pages, page) ? route : 'dashboard'
}

// Only a change to the directory filters remounts its list. Switching to a
// dossier or another tab keeps the operator's search, page and sort order.
export function routeMountKey(route) {
  if (route.split('?')[0] !== 'employees') return route
  const query = employeeDirectoryQuery(route)
  return 'employees' + (query.size ? '?' + query : '')
}

function employeeDirectoryQuery(route) {
  const query = new URLSearchParams(String(route || '').split('?')[1] || '')
  for (const key of ['employee', 'tab', 'evaluation']) query.delete(key)
  return query
}

export function profileHref(route, id, tab = 'general') {
  const query = employeeDirectoryQuery(route)
  if (id) { query.set('employee', String(id)); query.set('tab', tab) }
  return '#/employees' + (query.size ? '?' + query : '')
}

export function customTabId(tab) {
  const match = /^custom-([1-9]\d*)$/.exec(tab || '')
  if (!match) return null
  const id = Number(match[1])
  return Number.isSafeInteger(id) ? id : null
}

export function employeeRouteTarget(hash, tabs) {
  const query = new URLSearchParams(String(hash || '').split('?')[1] || '')
  const rawId = query.get('employee') || ''
  const id = /^[1-9]\d*$/.test(rawId) ? Number(rawId) : null
  const rawEvaluation = query.get('evaluation') || ''
  const evaluationId = /^[1-9]\d*$/.test(rawEvaluation) ? Number(rawEvaluation) : null
  const requested = query.get('tab')
  const tab = tabs.includes(requested) || (Number.isSafeInteger(id) && customTabId(requested)) ? requested : 'general'
  return {
    employeeId: Number.isSafeInteger(id) ? id : null,
    tab,
    ...(Number.isSafeInteger(id) && tab === 'candidate' && Number.isSafeInteger(evaluationId) ? { evaluationId } : {}),
  }
}

// Dashboard links use existing server filters; no extra status or metric is invented.
export function employeeDirectoryTarget(hash) {
  const query = new URLSearchParams(String(hash || '').split('?')[1] || '')
  const status = query.get('status') || ''
  return {
    search: (query.get('search') || '').trim().slice(0, 200),
    profile_status: ['draft', 'in_review', 'verified', 'archived'].includes(status) ? status : '',
    create: query.get('create') === '1',
  }
}
