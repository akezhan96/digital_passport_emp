import React, { useState } from 'react'
import { errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { worklistText } from '../i18n/worklists'
import { vacancyText } from '../i18n/vacancyMethodology'
import { recruitmentText } from '../i18n/recruitment'
import { recruitmentExplanation, recruitmentReason, resultScore, recruitmentLink, decisionClass, decisionTone } from '../recruitment'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { confirmUnsavedLeave } from '../unsavedChanges'
import ResultAppointmentForm from './ResultAppointmentForm'

export default function MatchingResultCard({ row, namesRevealed, onReveal, onDecision, onAppointed }) {
  const { t, pick, labelCode, lang } = useI18n()
  const { isAdmin } = useAuth()
  const c = recruitmentText(lang), v = vacancyText(lang), l = worklistText[lang] || worklistText.ru
  const e = row.explanation || {}, summary = row.methodology_summary
  const candidate = e.kind === 'candidate_methodology', score = resultScore(row, lang)
  const explain = value => recruitmentExplanation(value, lang)
  const [editing, setEditing] = useState(!row.decision)
  const [appointing, setAppointing] = useState(false)
  const savedCode = row.decision?.decision
  const status = row.appointment ? 'appointed' : savedCode
  const profile = tab => recruitmentLink('employees', { employee: row.employee_id, tab })
  const nextMessage = { selected: c.selectedNext, on_hold: c.onHoldNext, reserve: c.reserveNext, rejected: c.rejectedNext }[savedCode] || c.undecidedNext
  return <>
    <div className="card">
      <div className="recruitment-result-heading"><div><h3>{row.display_name}</h3>
        <span className="muted">{t('matching.rank')} {row.system_rank} · {candidate ? row.is_qualified ? v.complete : v.review : labelCode(row.readiness_code)}</span>
      </div><div className="recruitment-score"><strong>{score.percent}</strong>{score.points && <span>{score.points} {l.points}</span>}</div></div>
      {summary && <p className="muted recruitment-context">{pick(summary)} · v{summary.version} · {l.filled}: {summary.filled_count} / {summary.applicable_count}</p>}
      {summary?.partial_visibility && <p className="muted">{l.partialScore}</p>}
      {candidate && row.source_state?.stale && <div className="alert alert-warn">{v.sourceChanged}</div>}
      {!row.is_qualified && <div className="alert alert-warn recruitment-review"><strong>{candidate ? v.review : t('matching.criticalFailures')}</strong>
        {(e.critical_failures || []).map((failure, index) => <div key={index}>· {recruitmentReason(pick(failure, 'requirement') || failure.requirement, failure.detail, lang)}</div>)}
      </div>}
    </div>
    <div className={`card recruitment-decision ${status ? `status-surface ${decisionTone(status)}` : ''}`}>
      <div className="recruitment-result-heading"><h3>{t('matching.decision')}</h3>
        <span className={`badge ${decisionClass(status)}`}>{c[status] || c.noDecision}</span></div>
      {row.decision && <>
        <p className="muted recruitment-context">{c.decisionBy}: {row.decision.decided_by} · {new Date(row.decision.decided_at).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU')}</p>
        {row.decision.reason && <p className="recruitment-reason">{row.decision.reason}</p>}
      </>}
      {row.appointment ? <div className="recruitment-next"><strong>{c.appointmentDate}: {row.appointment.effective_date}</strong>
        <p>{pick(row.appointment, 'position')} · {pick(row.appointment, 'org_unit')}</p></div> : <p>{nextMessage}</p>}
      <div className="worklist-toolbar recruitment-actions">
        <a className="btn btn-ghost btn-sm" href={recruitmentLink('vacancies', { vacancy: row.vacancy_id })}>{c.viewVacancy}</a>
        {namesRevealed ? <><a className="btn btn-ghost btn-sm" href={profile('candidate')}>{!row.is_qualified ? c.reviewProfile : c.viewProfile}</a>
          {row.appointment && <a className="btn btn-ghost btn-sm" href={profile('career')}>{c.viewCareer}</a>}</>
          : <button className="btn btn-ghost btn-sm" onClick={onReveal}>{t('matching.revealNames')}</button>}
        {isAdmin && !row.appointment && !editing && <button className="btn btn-ghost btn-sm" onClick={() => { if (confirmUnsavedLeave()) { setAppointing(false); setEditing(true) } }}>{c.editDecision}</button>}
      </div>
      {isAdmin && !row.appointment && editing && <DecisionForm row={row} onDecision={onDecision} onSaved={() => setEditing(false)} onCancel={row.decision ? () => setEditing(false) : null} />}
      {savedCode === 'selected' && !row.appointment && !editing && <div className="recruitment-next">
        {!namesRevealed ? <p className="muted">{c.revealForAction}</p> : isAdmin && row.action_state?.can_appoint
          ? !appointing && <button className="btn" onClick={() => setAppointing(true)}>{c.appoint}</button>
          : <p className="muted">{c[row.action_state?.reason_code] || c.appointmentBlocked}</p>}
      </div>}
    </div>
    {appointing && namesRevealed && !editing && <ResultAppointmentForm result={row} onDone={onAppointed} onCancel={() => setAppointing(false)} />}
    <details className="card flush worklist-section"><summary>{c.details}</summary>
      <div className="worklist-table-scroll"><table><thead>{candidate
        ? <tr><th>{v.indicator}</th><th className="num">{v.points}</th><th className="num">{v.maximum}</th></tr>
        : <tr><th>{t('matching.requirement')}</th><th>{t('matching.fact')}</th><th className="num">{t('common.weight')}</th><th className="num">{t('matching.contribution')}</th><th>{t('common.status')}</th></tr>}</thead>
        <tbody>{candidate ? (e.criteria || []).map((criterion, index) => <tr key={criterion.id || index}><td>{index + 1}. {pick(criterion)}</td><td className="num">{criterion.points ?? '—'}</td><td className="num">{criterion.max_points}</td></tr>)
          : (e.requirements || []).map((requirement, index) => <tr key={index}><td>{pick(requirement, 'label')}</td><td>{explain(requirement.fact)}</td><td className="num">{requirement.weight}</td><td className="num">{requirement.contribution}</td><td>{t(`matching.statusLabel.${requirement.status}`)}</td></tr>)}</tbody>
      </table></div>
      {candidate && summary?.evaluated_at && <p className="muted recruitment-context">{v.savedAt}: {new Date(summary.evaluated_at).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU')} · {v.revision}: {summary.evaluation_revision}</p>}
      {e.gaps?.length > 0 && <div className="recruitment-gaps"><strong>{t('matching.gaps')}</strong>{e.gaps.map((gap, index) => <p key={index}>{recruitmentReason(pick(gap, 'requirement') || gap.requirement, gap.detail, lang)}</p>)}</div>}
    </details>
  </>
}

function DecisionForm({ row, onDecision, onSaved, onCancel }) {
  const { t, lang } = useI18n(), c = recruitmentText(lang)
  const scope = `matching-decision-${row.id}`
  const [decision, setDecision] = useState(row.decision?.decision || '')
  const [rank, setRank] = useState(row.decision?.final_rank || row.system_rank)
  const [reason, setReason] = useState(row.decision?.reason || '')
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const markSaved = useUnsavedChanges(dirty, c.decisionDirty, scope)
  const divergent = Number(rank) !== row.system_rank
  const needsReviewReason = decision === 'selected' && !row.is_qualified
  const reasonRequired = divergent || needsReviewReason
  const submit = async event => {
    event.preventDefault()
    if (!decision || busy || reasonRequired && !reason.trim()) return
    setBusy(true); setError('')
    try { await onDecision({ decision, final_rank: Number(rank), reason: reason.trim() || null }); markSaved(); setDirty(false); onSaved() }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  return <form className="recruitment-decision-form" onSubmit={submit}>
    {error && <div className="alert alert-bad" role="alert">{error}</div>}
    <div className="form-row"><div className="field"><label htmlFor="candidate-decision">{t('matching.decision')}</label>
      <select id="candidate-decision" required disabled={busy} value={decision} onChange={event => { setDecision(event.target.value); setDirty(true) }}><option value="">—</option>
        {['selected','on_hold','reserve','rejected'].map(code => <option key={code} value={code}>{c[code]}</option>)}</select></div>
      <div className="field"><label htmlFor="candidate-rank">{t('matching.rank')}</label><input id="candidate-rank" type="number" required min={1} step={1} disabled={busy} value={rank} onChange={event => { setRank(event.target.value); setDirty(true) }} /></div></div>
    <div className="field"><label htmlFor="candidate-reason">{t('audit.reason')}{reasonRequired ? ' *' : ''}</label><textarea id="candidate-reason" required={reasonRequired} maxLength={2000} rows={2} disabled={busy} value={reason} onChange={event => { setReason(event.target.value); setDirty(true) }} /></div>
    {reasonRequired && <p className="muted">{needsReviewReason ? c.reviewReason : t('matching.decisionReasonRequired')}</p>}
    <div className="worklist-toolbar"><button className="btn" disabled={busy || !decision || reasonRequired && !reason.trim()}>{busy ? c.saving : c.saveDecision}</button>
      {onCancel && <button type="button" disabled={busy} className="btn btn-ghost" onClick={() => { if (confirmUnsavedLeave(scope)) onCancel() }}>{t('common.cancel')}</button>}</div>
  </form>
}
