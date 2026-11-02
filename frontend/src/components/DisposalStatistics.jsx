import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import WorklistPager from './WorklistPager'
import './disposalStatistics.css'

export const disposalText = {
  ru: { title: 'В распоряжении', day: 'На дату', count: 'Сотрудников в распоряжении',
    average: 'Средний срок, дней', longest: 'Наибольший срок, дней', unit: 'Подразделение на дату вывода',
    all: 'Вся организация', noUnit: 'Не указано', employee: 'Сотрудник', since: 'Дата вывода',
    duration: 'Дней в распоряжении', empty: 'На эту дату в распоряжении никого нет.',
    retry: 'Повторить', loading: 'Загрузка…', breakdown: 'По подразделениям' },
  kk: { title: 'Қарамақтағы қызметкерлер', day: 'Есеп күні', count: 'Қарамақтағы қызметкерлер саны',
    average: 'Орташа мерзім, күн', longest: 'Ең ұзақ мерзім, күн', unit: 'Қарамаққа шығару кезіндегі бөлімше',
    all: 'Бүкіл ұйым', noUnit: 'Көрсетілмеген', employee: 'Қызметкер', since: 'Қарамаққа шығарылған күн',
    duration: 'Қарамақта болған күн саны', empty: 'Көрсетілген күні қарамақта қызметкер жоқ.',
    retry: 'Қайталау', loading: 'Жүктелуде…', breakdown: 'Бөлімшелер бойынша' },
}

const PAGE_SIZE = 20
function formatDate(iso) {
  return iso?.split('-').reverse().join('.') || '—'
}

export default function DisposalStatistics() {
  const { lang, pick, t } = useI18n()
  const copy = disposalText[lang] || disposalText.ru
  const [scope, setScope] = useState({ unit: '', offset: 0, reveal: false })
  const [revision, setRevision] = useState(0)
  const [response, setResponse] = useState(null)
  const [units, setUnits] = useState([])
  const nextRefresh = response?.data?.next_refresh_at
  // A dossier can be updated in another window while this list stays open.
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1)
    const now = new Date()
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    const serverMidnight = Date.parse(nextRefresh)
    const deadline = Number.isFinite(serverMidnight) && serverMidnight > now ? serverMidnight : midnight.getTime()
    const timer = setTimeout(refresh, Math.max(1000, deadline - now + 1000))
    window.addEventListener('focus', refresh)
    return () => { clearTimeout(timer); window.removeEventListener('focus', refresh) }
  }, [revision, nextRefresh])
  useEffect(() => {
    const controller = new AbortController()
    api.disposalStatistics({ org_unit_id: scope.unit ? Number(scope.unit) : undefined,
      offset: scope.offset, limit: PAGE_SIZE, reveal_names: scope.reveal }, controller.signal)
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setUnits(data.units)
        if (scope.offset && scope.offset >= data.total) {
          setScope(old => ({ ...old, offset: Math.floor(Math.max(0, data.total - 1) / PAGE_SIZE) * PAGE_SIZE }))
        } else setResponse({ scope, revision, data })
      }).catch(error => { if (!controller.signal.aborted) setResponse({ scope, revision, error }) })
    return () => controller.abort()
  }, [scope, revision])
  const current = response?.scope === scope && response.revision === revision ? response : null
  const data = current?.data
  function changeUnit(unit) { setScope({ unit, offset: 0, reveal: false }) }
  return <section className="card disposal-stats" aria-labelledby="disposal-title">
    <header><h3 id="disposal-title">{copy.title}</h3>
      {data && <span className="muted">{copy.day} · {formatDate(data.as_of)}</span>}
    </header>
    <label className="disposal-unit">{copy.unit}
      <select value={scope.unit} onChange={event => changeUnit(event.target.value)}>
        <option value="">{copy.all}</option>
        {units.filter(item => item.org_unit).map(item =>
          <option key={item.org_unit.id} value={item.org_unit.id}>{pick(item.org_unit)} ({item.count})</option>)}
        {scope.unit && !units.some(item => String(item.org_unit?.id) === scope.unit) &&
          <option value={scope.unit}>{copy.unit} · {scope.unit}</option>}
      </select>
    </label>
    {!current && <p role="status" className="muted">{copy.loading}</p>}
    {current?.error && <p className="alert alert-bad" role="alert">{errorMessage(current.error)}{' '}
      <button type="button" className="btn btn-sm btn-ghost" onClick={() => setRevision(value => value + 1)}>{copy.retry}</button></p>}
    {data && <>
      <dl className="disposal-counts">{[[copy.count, data.total], [copy.average, data.average_days], [copy.longest, data.max_days]]
        .map(([label, value]) => <div key={label}><dt>{label}</dt>
          <dd>{value == null ? '—' : value.toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU')}</dd></div>)}</dl>
      {data.total > 0 ? <>
        <div className="disposal-tools"><button type="button" className="btn btn-sm btn-ghost"
          aria-pressed={scope.reveal} title={t('matching.revealHint')}
          onClick={() => setScope(old => ({ ...old, reveal: !old.reveal }))}>
          {t(scope.reveal ? 'matching.hideNames' : 'matching.revealNames')}</button></div>
        <div className="disposal-table"><table><caption className="sr-only">{copy.title}</caption>
          <thead><tr>{[copy.employee, copy.unit, copy.since, copy.duration].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody>{data.items.map(row => <tr key={row.employee_id}><th scope="row">{data.names_revealed
            ? <a href={`#/employees?employee=${row.employee_id}&tab=career`}>{row.display_name}</a> : row.display_name}</th>
            <td>{pick(row.org_unit) || copy.noUnit}</td><td>{formatDate(row.since)}</td><td>{row.duration_days}</td>
          </tr>)}</tbody></table></div>
        {data.total > PAGE_SIZE && <WorklistPager total={data.total} offset={scope.offset} limit={PAGE_SIZE}
          onChange={offset => setScope(old => ({ ...old, offset }))} />}
        {!scope.unit && data.units.length > 0 && <details><summary>{copy.breakdown}</summary>
          <ul>{data.units.map(item => <li key={item.org_unit?.id || 'unknown'}>
            {pick(item.org_unit) || copy.noUnit} · <strong>{item.count}</strong></li>)}</ul></details>}
      </> : <p className="empty">{copy.empty}</p>}
    </>}
  </section>
}
