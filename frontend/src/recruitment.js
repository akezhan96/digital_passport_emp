import { localizeText } from './i18n/text.js'

// Saved calculations contain both older strings and bilingual objects.
// Always return text that React can render, including incomplete snapshots.
export function recruitmentExplanation(value, lang = 'ru') {
  if (value == null) return ''
  if (typeof value === 'object') {
    const localized = value[lang] ?? value.ru ?? value.kk
    return typeof localized === 'string' ? localizeText(localized, lang) : ''
  }
  return String(localizeText(String(value), lang))
}

export function resultScore(row, lang = 'ru') {
  const legacyCalculation = row.explanation?.kind !== 'candidate_methodology' && row.explanation?.requirements
  const summary = legacyCalculation ? null : row.methodology_summary ?? row.explanation?.methodology_summary
  const format = value => Number(value).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU', { maximumFractionDigits: 2 })
  const assessed = row.readiness_code !== 'not_assessed'
  const percent = summary ? summary.percent : row.score
  return {
    percent: assessed && percent != null && Number.isFinite(Number(percent)) ? `${format(percent)}%` : '—',
    points: summary?.earned_points != null && summary?.max_points != null
      && Number.isFinite(Number(summary.earned_points)) && Number.isFinite(Number(summary.max_points))
      ? `${format(summary.earned_points)} / ${format(summary.max_points)}` : null,
  }
}

export function recruitmentReason(requirement, detail, lang = 'ru') {
  const label = recruitmentExplanation(requirement, lang).trim()
  const explanation = recruitmentExplanation(detail, lang).trim()
  return [...new Set([label, explanation].filter(Boolean))].join(' — ')
}

export const recruitmentLink = (page, params = {}) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value != null && value !== '').map(([key, value]) => [key, String(value)]))
  return `#/${page}${query.size ? `?${query}` : ''}`
}

export function recruitmentQuery(hash = globalThis.location?.hash || '') {
  const query = new URLSearchParams(hash.split('?')[1] || '')
  const id = key => /^\d+$/.test(query.get(key) || '') && Number.isSafeInteger(Number(query.get(key))) && Number(query.get(key)) > 0 ? Number(query.get(key)) : null
  return { vacancy: id('vacancy'), run: id('run'), result: id('result'), names: query.get('names') === '1' }
}

export const decisionClass = decision => decision === 'selected' ? 'badge-ok'
  : ['appointed', 'reserve'].includes(decision) ? 'badge-info'
  : decision === 'rejected' ? 'badge-bad' : decision === 'on_hold' ? 'badge-warn' : 'badge-mute'

export const decisionTone = decision => decision === 'selected' ? 'status-positive'
  : ['appointed', 'reserve'].includes(decision) ? 'status-info'
  : decision === 'rejected' ? 'status-negative' : decision === 'on_hold' ? 'status-warning' : 'status-neutral'
