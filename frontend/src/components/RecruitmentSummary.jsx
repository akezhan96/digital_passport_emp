import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { recruitmentText } from '../i18n/recruitment'
import { worklistText } from '../i18n/worklists'
import { recruitmentLink, resultScore, decisionClass, decisionTone } from '../recruitment'
import { recruitmentActions } from '../workflowUi'
import WorklistPager from './WorklistPager'

export default function RecruitmentSummary({ vacancy, onChanged }) {
  const { t, pick, lang } = useI18n(), { isAdmin } = useAuth()
  const c = recruitmentText(lang), l = worklistText[lang] || worklistText.ru
  const [data, setData] = useState(null), [error, setError] = useState('')
  const [names, setNames] = useState(false), [status, setStatus] = useState(''), [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0), [closing, setClosing] = useState(false)
  useEffect(() => {
    let live = true
    setData(null); setError('')
    api.vacancyRecruitment(vacancy.id, { reveal_names: names, status: status || undefined, offset, limit: 10 })
      .then(response => { if (live) setData(response.data) })
      .catch(e => { if (live) setError(errorMessage(e)) })
    return () => { live = false }
  }, [vacancy.id, vacancy.status, names, status, offset, refresh])
  const close = async () => {
    if (!window.confirm(c.closeConfirm)) return
    setClosing(true); setError('')
    try { await api.vacancyUpdate(vacancy.id, { status: 'closed' }); onChanged() }
    catch (e) { setError(errorMessage(e)) }
    finally { setClosing(false) }
  }
  const link = row => recruitmentLink('matching', { run: row.run_id, result: row.result_id, names: names ? 1 : undefined })
  return <section className="card recruitment-summary" aria-label={c.recruitment}>
    <div className="recruitment-result-heading"><h3>{c.recruitment}</h3>
      {data && <RecruitmentActions vacancy={vacancy} latestRun={data.latest_run} names={names} />}</div>
    {error && <div className="alert alert-bad" role="alert">{error} <button className="btn btn-ghost btn-sm" onClick={() => setRefresh(value => value + 1)}>{c.retry}</button></div>}
    {!data && !error ? <div className="spinner" /> : data && <>
      <div className="recruitment-metrics">
        {[[c.runs, data.counts.runs,''],[c.selectedCount, data.counts.selected,'status-positive'],[c.appointedCount, data.counts.appointed,'status-info'],[c.reserve,data.counts.reserve,'status-info']].map(([label,value,tone]) => <div key={label} className={value > 0 && tone ? `status-surface ${tone}` : ''}><strong>{value}</strong><span>{label}</span></div>)}
      </div>
      {data.latest_run ? <div className="recruitment-latest"><span>{c.lastRun}: № {data.latest_run.id} · {c.considered}: {data.latest_run.total_evaluated}</span>
        <a href={recruitmentLink('matching', { run: data.latest_run.id, names: names ? 1 : undefined })}>{l.results}</a></div>
        : <p className="muted">{c.noRuns}</p>}
      <div className="worklist-toolbar recruitment-candidate-toolbar"><h4>{c.selectedCandidates}</h4>
        <select aria-label={t('matching.decision')} value={status} onChange={event => { setStatus(event.target.value); setOffset(0) }}>
          <option value="">{l.all}</option>{['selected','appointed','on_hold','reserve','rejected'].map(code => <option key={code} value={code}>{c[code]}</option>)}</select>
        <button className="btn btn-ghost btn-sm" onClick={() => setNames(value => !value)}>{names ? t('matching.hideNames') : t('matching.revealNames')}</button>
      </div>
      {!data.candidates.length ? <div className="recruitment-empty"><p>{status ? l.noResults : c.noDecisions}</p>{!status && data.latest_run && <p className="muted">{c.noSelectionsNext}</p>}</div>
        : <div className="recruitment-candidates">{data.candidates.map(row => <article key={row.employee_id} className={`recruitment-candidate status-surface ${decisionTone(row.status_code)}`}>
          <div className="recruitment-result-heading">{row.run_id && row.result_id ? <a className="recruitment-name" href={link(row)}>{row.display_name}</a> : <strong>{row.display_name}</strong>}
            <span className={`badge ${decisionClass(row.status_code)}`}>{c[row.status_code] || c.noDecision}</span></div>
          <div className="recruitment-result-heading"><span className="muted">{row.appointment ? `${c.appointmentDate}: ${row.appointment.effective_date}` : row.status_code === 'selected' ? c.awaitingAppointment : row.decision?.decided_at?.slice(0, 10)}</span>
            <span className="recruitment-candidate-score"><strong>{resultScore(row, lang).percent}</strong>{resultScore(row, lang).points && <> · {resultScore(row, lang).points} {l.points}</>}</span></div>
          {row.appointment && <p>{pick(row.appointment, 'position')} · {pick(row.appointment, 'org_unit')}</p>}
          {row.decision?.reason && <p className="recruitment-reason">{row.decision.reason}</p>}
          <div className="worklist-toolbar">{row.run_id && row.result_id && <a href={link(row)}>{isAdmin && row.status_code === 'selected' && vacancy.status !== 'closed' ? c.appoint : c.openResult}</a>}
            {names && <a href={recruitmentLink('employees', { employee: row.employee_id, tab: row.appointment ? 'career' : 'candidate' })}>{row.appointment ? c.viewCareer : c.viewProfile}</a>}</div>
        </article>)}</div>}
      {data.total > 10 && <WorklistPager total={data.total} offset={offset} limit={10} onChange={setOffset} />}
    </>}
    {vacancy.status === 'closed' ? <p className="muted recruitment-close">{c.vacancyClosed}</p> : isAdmin && <div className="recruitment-close"><span className="muted">{c.closeHint}</span><button className="btn btn-ghost btn-sm" disabled={closing} onClick={close}>{c.closeVacancy}</button></div>}
  </section>
}

export function RecruitmentActions({ vacancy, latestRun, names = false }) {
  const { lang } = useI18n(), c = recruitmentText(lang)
  const { primary, secondary } = recruitmentActions(vacancy, latestRun)
  const render = (action, main) => action && <a className={`btn btn-sm${main ? '' : ' btn-ghost'}`} href={recruitmentLink('matching', action.kind === 'results'
    ? { run: action.run, names: names ? 1 : undefined } : { vacancy: action.vacancy })}>
    {action.kind === 'results' ? c.openResults : action.kind === 'rerun' ? c.rerunMatching : c.startMatching}</a>
  return <div className="worklist-toolbar">{render(primary, true)}{render(secondary, false)}</div>
}

