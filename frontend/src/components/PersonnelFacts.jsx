import React, { useEffect, useState } from 'react'
import { errorMessage } from '../api'
import { personnelApi } from '../personnelApi'
import { useI18n } from '../i18n'
import { personnelText, dateLabel, dayCount, localToday } from '../i18n/personnel'
import { CANDIDATE_SCOPE } from '../unsavedChanges'
import { useFormChanges } from '../useFormChanges'

export const personnelScope = `${CANDIDATE_SCOPE}:personnel`
const kinds = ['contract', 'rank', 'recognition']

export function useCareerFacts(employeeId, revision) {
  const [snapshot, setSnapshot] = useState(null)
  const [refresh, setRefresh] = useState(0)
  const nextRefresh = snapshot?.employeeId === employeeId ? snapshot.summary?.next_refresh_at : null
  useEffect(() => {
    const reload = () => setRefresh(n => n + 1)
    const serverMidnight = Date.parse(nextRefresh)
    const localMidnight = new Date()
    localMidnight.setHours(24, 0, 0, 0)
    const wake = Number.isFinite(serverMidnight) && serverMidnight > Date.now() ? serverMidnight : localMidnight.getTime()
    const timer = setTimeout(reload, wake - Date.now() + 1000)
    function onReturn() { if (document.visibilityState === 'visible') reload() }
    document.addEventListener('visibilitychange', onReturn)
    return () => { clearTimeout(timer); document.removeEventListener('visibilitychange', onReturn) }
  }, [employeeId, nextRefresh, refresh])
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal
    Promise.all([personnelApi.summary(employeeId, signal), personnelApi.disposals(employeeId, signal), personnelApi.records(employeeId, signal)])
      .then(([summary, disposals, records]) => {
        if (!signal.aborted) setSnapshot({ employeeId, summary: summary.data, disposals: disposals.data.data, records: records.data.items })
      }).catch(error => {
        if (!signal.aborted) setSnapshot({ employeeId, error: errorMessage(error) })
      })
    return () => controller.abort()
  }, [employeeId, revision, refresh])
  return snapshot?.employeeId === employeeId ? snapshot : null
}

export function PersonnelForm({ employeeId, record, onBusy, busy, onError, onConflict, onSaved, onCancel }) {
  const { t, lang } = useI18n(), c = personnelText(lang)
  const defaults = { kind: 'contract', title: '', event_date: '', end_date: '', planned_date: '', indefinite: false }
  const [form, setForm] = useState(() => Object.fromEntries(Object.entries(defaults).map(([key, v]) => [key, record?.[key] ?? v])))
  const accept = useFormChanges(form, { scope: personnelScope })
  function update(key, value) { setForm(old => ({ ...old, [key]: value })) }
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    onBusy(true); onError(null)
    try {
      const body = { kind: form.kind, title: form.title.trim(), event_date: form.event_date }
      if (form.kind === 'contract') Object.assign(body, { indefinite: form.indefinite, end_date: form.indefinite ? null : form.end_date || null })
      if (form.kind === 'rank') body.planned_date = form.planned_date || null
      await personnelApi.save(employeeId, record, body)
      accept(); onSaved()
    } catch (error) {
      onError(errorMessage(error))
      if (error.response?.status === 409) onConflict()
    } finally { onBusy(false) }
  }
  return <form onSubmit={submit}><fieldset className="career-form-fields" disabled={busy}>
    <label className="field">{c.type}<select value={form.kind} disabled={Boolean(record)}
      onChange={e => update('kind', e.target.value)}>
      {kinds.map(k => <option key={k} value={k}>{c[k]}</option>)}</select></label>
    <label className="field">{c[form.kind + 'Title']}<input required={form.kind !== 'contract'} maxLength={180}
      value={form.title} onChange={e => update('title', e.target.value)} /></label>
    <label className="field">{c[form.kind + 'Date']}<input required type="date" max={localToday()}
      value={form.event_date} onChange={e => update('event_date', e.target.value)} /></label>
    {form.kind === 'contract' && <>
      <label className="checkbox"><input type="checkbox" checked={form.indefinite}
        onChange={e => update('indefinite', e.target.checked)} />{c.indefinite}</label>
      {!form.indefinite && <label className="field">{c.endDate}<input type="date" min={form.event_date || undefined}
        value={form.end_date} onChange={e => update('end_date', e.target.value)} /></label>}
    </>}
    {form.kind === 'rank' && <label className="field">{c.plannedDate}<input type="date" min={form.event_date || undefined}
      value={form.planned_date} onChange={e => update('planned_date', e.target.value)} /></label>}
    <div className="btn-row"><button type="submit" className="btn">{t('common.save')}</button>
      <button type="button" className="btn btn-ghost" onClick={onCancel}>{t('common.cancel')}</button></div>
  </fieldset></form>
}

function tenureYears(days, lang) {
  if (days < 365.25) return ''
  const format = new Intl.NumberFormat(lang === 'kk' ? 'kk-KZ' : 'ru-RU',
    { style: 'unit', unit: 'year', unitDisplay: 'long', maximumFractionDigits: 1 })
  return '≈ ' + format.format(days / 365.25)
}

function SummaryItem({ label, value, children }) {
  return <div className="personnel-fact"><dt>{label}</dt><dd><strong>{value}</strong>{children}</dd></div>
}

export function PersonnelFacts({ snapshot, canWrite, busy, openDialog, remove, retry }) {
  const { t, lang } = useI18n(), c = personnelText(lang)
  const days = n => dayCount(n, lang)
  if (!snapshot) return <p className="career-notice" role="status">{t('common.loading')}</p>
  if (snapshot.error) return <p className="alert alert-bad" role="alert">{snapshot.error}{' '}
    <button type="button" className="btn btn-ghost btn-sm" onClick={retry}>{t('errors.retry')}</button></p>
  const { summary, disposals, records } = snapshot
  const { tenure, contract, rank, recognition } = summary
  let contractTerm = ''
  if (contract) {
    const labels = { unknown: c.unknownEnd, indefinite: c.indefinite, expires_today: c.today,
      expired: c.overdue + ' · ' + days(Math.abs(contract.remaining_days)), valid: c.remaining + ' ' + days(contract.remaining_days) }
    contractTerm = labels[contract.status]
  }
  const nextRankDays = rank?.until_planned_days
  const nextRankTerm = nextRankDays === 0 ? c.dueToday : (nextRankDays > 0 ? c.due : c.past) + ' ' + days(Math.abs(nextRankDays))
  const disposalTotal = disposals.reduce((sum, r) => sum + r.days, 0)
  const totalYears = tenure.has_work_periods && tenureYears(tenure.total_days, lang)
  const companyYears = tenure.has_work_periods && tenureYears(tenure.company_days, lang)
  return <section className="card career-facts">
    <header className="career-heading"><h3>{c.summary}</h3><small>{c.asOf} {dateLabel(summary.as_of)}</small></header>
    <dl className="personnel-grid">
      <SummaryItem label={c.total} value={tenure.has_work_periods ? totalYears || days(tenure.total_days) : c.noData}>
        {totalYears && <small>{days(tenure.total_days)}</small>}
        {tenure.has_work_periods && <small>{c.company} · {companyYears && companyYears + ' · '}{days(tenure.company_days)}</small>}
        {disposals.length > 0 && <small>{c.disposal} · {days(disposalTotal)}</small>}
      </SummaryItem>
      <SummaryItem label={c.contract} value={contract ? contractTerm : c.noData}>
        {contract && <><small>{c.signed} · {dateLabel(contract.event_date)}</small>
          {contract.end_date && <small>{c.expiry} · {dateLabel(contract.end_date)}</small>}</>}
      </SummaryItem>
      <SummaryItem label={c.rank} value={rank?.title || c.noData}>
        {rank && <><small>{c.received} · {dateLabel(rank.event_date)}</small><small>{c.elapsed} · {days(rank.elapsed_days)}</small>
          {rank.planned_date && <small>{c.planned} · {dateLabel(rank.planned_date)} ({nextRankTerm})</small>}</>}
      </SummaryItem>
      <SummaryItem label={c.recognition} value={recognition?.title || c.noData}>
        {recognition && <><small>{c.rewarded} · {dateLabel(recognition.event_date)}</small>
          <small>{c.elapsed} · {days(recognition.elapsed_days)}</small></>}
      </SummaryItem>
    </dl>
    {disposals.length > 0 && <small className="personnel-note">{c.tenureNote}</small>}
    <details className="personnel-register"><summary>{c.records} ({records.length})</summary>
      {canWrite && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => openDialog('record')}>{c.add}</button>}
      {!records.length && <p className="career-notice">{c.empty}</p>}
      {records.map(row => <div className="personnel-record" key={row.id}>
        <div><strong>{row.title || c[row.kind]}</strong><small>{row.title ? c[row.kind] + ' · ' : ''}
          {dateLabel(row.event_date)}{row.end_date && ' – ' + dateLabel(row.end_date)}
          {row.indefinite && ' · ' + c.indefinite}
          {row.planned_date && ' · ' + c.planned + ' ' + dateLabel(row.planned_date)}</small></div>
        {canWrite && <div className="btn-row"><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => openDialog('record', row)}>{t('edit.edit')}</button>
          <button className="btn btn-ghost btn-sm danger" disabled={busy} onClick={() => remove(row)}>{t('common.delete')}</button></div>}
      </div>)}
    </details>
  </section>
}
