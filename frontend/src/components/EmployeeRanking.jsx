import React, { useEffect, useMemo, useState } from 'react'
import { api, errorMessage } from '../api'
import { candidateApi } from '../candidateApi'
import { useI18n } from '../i18n'
import { rankingText } from '../i18n/employeeRanking'
import WorklistPager from './WorklistPager'
import './employeeRanking.css'

const PAGE_SIZE = 10

function initialFilters() {
  // Back from a dossier restores the scope and page, without retaining names.
  const saved = window.history.state?.employeeRanking
  const unit = new URLSearchParams(location.hash.split('?')[1]).get('unit') || ''
  return { unit, method: '', subunits: true, offset: 0, ...saved, reveal: false }
}

function unitLabels(units, pick, lang) {
  const byId = new Map(units.map(unit => [unit.id, unit]))
  return units.map(unit => {
    const path = [], seen = new Set()
    for (let current = unit; current && !seen.has(current.id); current = byId.get(current.parent_id)) {
      seen.add(current.id); path.unshift(pick(current))
    }
    return { id: unit.id, label: path.join(' / ') }
  }).sort((left, right) => left.label.localeCompare(right.label, lang === 'kk' ? 'kk-KZ' : 'ru-RU', { numeric: true }))
}

export default function EmployeeRanking() {
  const { lang, t, pick } = useI18n()
  const copy = rankingText(lang)
  const [filters, setFilters] = useState(initialFilters)
  const [options, setOptions] = useState(null)
  const [optionError, setOptionError] = useState(null)
  const [retryOptions, setRetryOptions] = useState(0)
  const [answer, setAnswer] = useState(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let current = true
    setOptionError(null)
    Promise.all([candidateApi.models(), api.refList('org-units')])
      .then(([versions, units]) => {
        if (current) setOptions({ methods: versions.data.filter(m => ['active', 'archived'].includes(m.status)), units: units.data.data })
      }).catch(error => { if (current) setOptionError(error) })
    return () => { current = false }
  }, [retryOptions])
  const method = options?.methods.find(m => String(m.id) === filters.method)
    || options?.methods.find(m => m.status === 'active') || options?.methods[0]
  const units = useMemo(() => unitLabels(options?.units || [], pick, lang), [options, pick, lang])
  const validUnit = !filters.unit || units.some(unit => String(unit.id) === filters.unit)
  const request = useMemo(() => method && validUnit ? {
    methodology_id: method.id, org_unit_id: filters.unit ? Number(filters.unit) : undefined,
    include_subunits: filters.subunits, limit: PAGE_SIZE, offset: filters.offset, reveal_names: filters.reveal,
  } : null, [method, validUnit, filters])
  useEffect(() => {
    if (!request) return
    const controller = new AbortController()
    api.employeeRanking(request, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return
      if (request.offset && request.offset >= data.total) {
        setFilters(prev => ({ ...prev, offset: Math.floor(Math.max(0, data.total - 1) / PAGE_SIZE) * PAGE_SIZE }))
      } else setAnswer({ request, retry, data })
    }).catch(error => { if (!controller.signal.aborted) setAnswer({ request, retry, error }) })
    return () => controller.abort()
  }, [request, retry])
  const current = answer?.request === request && answer.retry === retry ? answer : null
  const data = current?.data
  // Keep controls mounted during paging and name reveal, but never reuse the previous rows.
  const sameScope = request && answer?.request && ['methodology_id', 'org_unit_id', 'include_subunits']
    .every(key => request[key] === answer.request[key])
  const counts = data || (sameScope && !current?.error ? answer.data : null)
  const busy = !optionError && (!options || Boolean(request && !current))
  function changeScope(changes) {
    setFilters(prev => ({ ...prev, ...changes, offset: 0, reveal: false }))
  }
  function rememberPage() {
    const { unit, subunits, offset } = filters
    window.history.replaceState({ ...window.history.state,
      employeeRanking: { unit, method: String(method.id), subunits, offset } }, '')
  }
  return <section className="card employee-ranking" aria-labelledby="employee-ranking-title">
    <header><h3 id="employee-ranking-title">{copy.title}</h3><p className="muted">{copy.hint}</p></header>
    {options?.methods.length > 0 && <div className="employee-ranking-filters">
      <label>{copy.methodology}<select value={method.id} onChange={e => changeScope({ method: e.target.value })}>
        {options.methods.map(m => <option key={m.id} value={m.id}>{pick(m)} · {copy.version} {m.version}{m.status === 'archived' ? ' · ' + copy.archived : ''}</option>)}
      </select></label>
      <label>{copy.scope}<select value={filters.unit} onChange={e => changeScope({ unit: e.target.value, subunits: true })}>
        <option value="">{copy.company}</option>
        {!validUnit && <option value={filters.unit}>{copy.unknownUnit}</option>}
        {units.map(unit => <option key={unit.id} value={unit.id}>{unit.label}</option>)}
      </select></label>
      {filters.unit && <label className="employee-ranking-check"><input type="checkbox" checked={filters.subunits}
        onChange={e => changeScope({ subunits: e.target.checked })} />{copy.children}</label>}
    </div>}
    {(optionError || current?.error) && <div className="alert alert-bad" role="alert">{errorMessage(optionError || current.error)}{' '}
      <button type="button" className="btn btn-sm btn-ghost" onClick={() => optionError ? setRetryOptions(x => x + 1) : setRetry(x => x + 1)}>{copy.retry}</button></div>}
    {options && !options.methods.length && <p className="empty">{copy.noMethod}</p>}
    {options?.methods.length > 0 && !validUnit && <p className="empty">{copy.unknownUnit}</p>}
    {counts && <div className="employee-ranking-summary">
      <div role="status">{copy.coverage} <strong>{counts.total}</strong> {copy.of} {counts.scope_total}
        {counts.excluded_count > 0 && <span className="muted"> · {copy.excluded} {counts.excluded_count}</span>}</div>
      {counts.total > 0 && <button type="button" className="btn btn-sm btn-ghost" aria-pressed={filters.reveal}
        title={t('matching.revealHint')} onClick={() => setFilters(prev => ({ ...prev, reveal: !prev.reveal }))}>
        {t(filters.reveal ? 'matching.hideNames' : 'matching.revealNames')}</button>}
    </div>}
    {busy && <p role="status" className="muted">{copy.loading}</p>}
    {data && <>
      {data.partial_visibility && <p className="alert alert-info">{copy.restricted}</p>}
      {data.items.length ? <RankingTable data={data} rememberPage={rememberPage} /> :
        <p className="empty">{!data.scope_total ? (filters.unit ? copy.emptyScope : copy.emptyCompany) : copy.noRatings}</p>}
    </>}
    {counts?.total > PAGE_SIZE && <nav aria-label={copy.title}><WorklistPager total={counts.total} offset={filters.offset} limit={PAGE_SIZE}
      onChange={offset => setFilters(prev => ({ ...prev, offset }))} /></nav>}
    {counts && <details className="employee-ranking-rules"><summary>{copy.details}</summary><p>{copy.rule}</p><p>{copy.denominator}</p></details>}
  </section>
}

export function RankingTable({ data, rememberPage }) {
  const { lang, pick } = useI18n()
  const copy = rankingText(lang)
  const number = new Intl.NumberFormat(lang === 'kk' ? 'kk-KZ' : 'ru-RU', { maximumFractionDigits: 2 })
  return <div className="employee-ranking-scroll"><table>
    <caption className="sr-only">{copy.title}</caption>
    <thead><tr>{[copy.rank, copy.employee, copy.scope, copy.points, copy.percent].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
    <tbody>{data.items.map(row => <tr key={row.employee_id}>
      <td><span className={'employee-ranking-place' + (row.rank <= 3 ? ' is-leading' : '')}>{row.rank}</span></td>
      <th scope="row">{data.names_revealed ? <a href={`#/employees?employee=${row.employee_id}&tab=candidate&evaluation=${row.evaluation_id}`}
        onClick={rememberPage} aria-label={`${copy.open}: ${row.display_name}`}>{row.display_name}</a> : row.display_name}</th>
      <td>{pick(row.org_unit) || copy.noUnit}</td>
      <td className="employee-ranking-points"><strong>{number.format(row.earned_points)}</strong> / {number.format(row.max_points)}</td>
      <td><div className="employee-ranking-percent">{number.format(row.percent)}%<span aria-hidden="true"><i style={{ width: row.percent + '%' }} /></span></div></td>
    </tr>)}</tbody>
  </table></div>
}
