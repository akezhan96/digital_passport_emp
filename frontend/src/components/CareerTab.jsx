import { renderDemo } from '../renderDemo'
import React, { useEffect, useId, useRef, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { personnelApi } from '../personnelApi'
import { dateLabel, dayCount, localToday, personnelText } from '../i18n/personnel'
import { PersonnelFacts, PersonnelForm, personnelScope, useCareerFacts } from './PersonnelFacts'
import { careerText } from '../i18n/career'
import { useFormChanges } from '../useFormChanges'
import { CANDIDATE_SCOPE, confirmUnsavedLeave } from '../unsavedChanges'
import AppointmentForm, { appointmentScope } from './AppointmentForm'
import Attachments from './Attachments'
import './career.css'

export function careerTimeline(detail, today = localToday()) {
  const periods = [...(detail.work_experience || [])].sort((a, b) =>
    String(b.date_from).localeCompare(String(a.date_from)) || b.id - a.id)
  const ongoing = detail.employment_status === 'active' && detail.profile_status !== 'archived'
    ? periods.filter(r => r.is_internal && r.date_from && r.date_from <= today && (!r.date_to || r.date_to >= today)) : []
  // Imported records may overlap. The dossier's current post is only a tie-breaker;
  // without a unique match the timeline shows all records instead of guessing.
  const knownPost = Boolean(detail.current_position_id || detail.current_org_unit_id)
  const matched = ongoing.filter(row => (!detail.current_position_id || row.position_id === detail.current_position_id)
    && (!detail.current_org_unit_id || row.org_unit_id === detail.current_org_unit_id))
  const current = matched.length === 1 ? matched[0] : null
  const conflict = knownPost && ongoing.length > 0 && !matched.length
  return { current, conflict, ambiguous: matched.length > 1, history: periods.filter(row => row !== current) }
}

function refName(catalog, id, refs, pick) {
  return pick((refs[catalog] || []).find(item => item.id === id))
}
function periodName(row, refs, pick, copy) {
  return (row.is_internal ? refName('positions', row.position_id, refs, pick) : row.external_position_title) || copy.missingRole
}
const periodScope = `${CANDIDATE_SCOPE}:career-period`

function CareerDialog({ title, busy, requestClose, error, children }) {
  const id = useId(), ref = useRef(null)
  const { t } = useI18n()
  useEffect(() => {
    const dialog = ref.current
    dialog.showModal()
    return () => dialog.close()
  }, [])
  function escape(event) {
    if (event.key !== 'Escape' || event.defaultPrevented || event.nativeEvent.isComposing) return
    // An open native option list owns the first Escape. Once it is closed,
    // handle the key before the browser can independently dismiss the dialog.
    if (event.target.tagName === 'SELECT' && globalThis.CSS?.supports('selector(select:open)')
      && event.target.matches(':open')) return
    event.preventDefault()
    event.stopPropagation()
    if (!event.repeat) requestClose(event)
  }
  return <dialog ref={ref} aria-labelledby={id} closedby="none" onCancel={requestClose} onKeyDown={escape} className="career-dialog">
    <div className="career-dialog-title"><h3 id={id}>{title}</h3>
      <button type="button" className="btn btn-ghost btn-sm" disabled={busy} aria-label={t('common.close')} onClick={requestClose}>×</button></div>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    {children}
  </dialog>
}

const initialPeriod = { is_internal: true, org_unit_id: null, position_id: null, external_employer: '', external_position_title: '',
  job_family_id: null, org_unit_type_id: null, country_id: null, date_from: '', date_to: '' }

function PeriodForm({ employeeId, row, refs, onBusy, busy, onError, onSaved, onCancel }) {
  const { t, pick, lang } = useI18n()
  const copy = careerText(lang)
  const [form, setForm] = useState(() => Object.fromEntries(Object.entries(initialPeriod)
    .map(([key, initial]) => [key, row?.[key] ?? initial])))
  const [reason, setReason] = useState('')
  const accept = useFormChanges({ form, reason }, { scope: periodScope })
  function change(key, value) { setForm(old => ({ ...old, [key]: value })) }
  function refField(key, catalog, label, required = false) {
    return <label className="field">{label}<select required={required} value={form[key] ?? ''}
      onChange={e => change(key, e.target.value ? Number(e.target.value) : null)}>
      <option value="">—</option>{(refs[catalog] || []).map(item => <option key={item.id} value={item.id}>{pick(item)}</option>)}
    </select></label>
  }
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    onBusy(true); onError(null)
    const body = { is_internal: form.is_internal, date_from: form.date_from, date_to: form.date_to || null,
      job_family_id: form.job_family_id, org_unit_type_id: form.org_unit_type_id, country_id: form.country_id }
    if (form.is_internal) Object.assign(body, { org_unit_id: form.org_unit_id, position_id: form.position_id })
    else Object.assign(body, { external_employer: form.external_employer.trim(), external_position_title: form.external_position_title.trim() })
    try {
      if (row) await api.updateChild('work-experience', row.id, { ...body, reason: reason.trim() || null })
      else await api.addCareer(employeeId, body)
      accept(); onSaved()
    } catch (error) { onError(errorMessage(error)) } finally { onBusy(false) }
  }
  return <form onSubmit={submit}><fieldset className="career-form-fields" disabled={busy}>
    {!row && <label className="field">{copy.place}<select value={form.is_internal ? 'internal' : 'external'}
      onChange={e => change('is_internal', e.target.value === 'internal')}>
      <option value="internal">{copy.internal}</option><option value="external">{copy.external}</option></select></label>}
    <div className="form-row">{form.is_internal ? <>
      {refField('org_unit_id','org-units',t('employee.career.orgUnit'))}
      {refField('position_id','positions',t('employee.career.position'))}
    </> : <>
      <label className="field">{t('employee.career.employer')}<input value={form.external_employer} required={!row}
        onChange={e => change('external_employer', e.target.value)} /></label>
      <label className="field">{t('employee.career.position')}<input value={form.external_position_title}
        onChange={e => change('external_position_title', e.target.value)} /></label>
    </>}</div>
    <div className="form-row">
      <label className="field">{t('employee.career.dateFrom')}<input type="date" required value={form.date_from}
        onChange={e => change('date_from',e.target.value)} /></label>
      <label className="field">{t('employee.career.dateTo')}<input type="date" value={form.date_to} min={form.date_from || undefined}
        onChange={e => change('date_to',e.target.value)} /></label>
    </div>
    <div className="form-row">
      {refField('job_family_id','job-families',t('employee.career.jobFamily'),true)}
      {refField('org_unit_type_id','org-unit-types',t('employee.career.unitType'),true)}
    </div>
    {refField('country_id','countries',t('employee.career.country'))}
    {row && <label className="field">{t('edit.reason')}<input value={reason} onChange={e => setReason(e.target.value)} /></label>}
    <div className="btn-row"><button className="btn" type="submit">{t('common.save')}</button>
      <button className="btn btn-ghost" type="button" onClick={onCancel}>{t('common.cancel')}</button></div>
  </fieldset></form>
}

function CareerPeriod({ row, refs, current = false, appointment, expanded, onToggle, openDialog, act, canWrite, busy }) {
  const { t, pick, lang } = useI18n(), copy = careerText(lang), panelId = useId()
  const position = periodName(row, refs, pick, copy)
  const unit = row.is_internal ? refName('org-units',row.org_unit_id,refs,pick) : row.external_employer
  const c = personnelText(lang)
  const dates = current && appointment
    ? (appointment.basis === 'appointment' ? c.appointed : c.onPost) + ' ' + dateLabel(appointment.since) + ' · ' + dayCount(appointment.duration_days, lang)
    : current && !row.date_to ? `${copy.currentFrom} ${dateLabel(row.date_from)}`
    : `${dateLabel(row.date_from)} – ${row.date_to ? dateLabel(row.date_to) : copy.open}`
  const metadata = [
    [copy.kind, row.is_appointment ? t('appointment.types.appointment') : c.manual],
    [t('employee.career.jobFamily'), refName('job-families',row.job_family_id,refs,pick)],
    [t('employee.career.unitType'), refName('org-unit-types',row.org_unit_type_id,refs,pick)],
    [t('employee.career.country'), refName('countries',row.country_id,refs,pick)],
    [copy.vacancy,row.source_vacancy], [t('appointment.reason'),row.reason],
  ].filter(([, value]) => value)
  return <div className={current ? 'career-period career-current' : 'career-period'}>
    <button className="career-period-toggle" type="button" title={expanded ? copy.less : copy.more} aria-expanded={expanded} aria-controls={expanded ? panelId : undefined}
      onClick={onToggle}><span className="career-period-identity"><strong>{position}</strong>{unit && <span>{unit}</span>}</span>
      <span className="career-period-dates">{dates}</span><span className="career-expand" aria-hidden="true">{expanded ? '▴' : '▾'}</span>
    </button>
    {expanded && <div className="career-period-detail" id={panelId}>
      {metadata.length > 0 && <dl>{metadata.map(([name,value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
      <div className="btn-row">{!renderDemo && <button className="btn btn-ghost btn-sm" type="button"
        onClick={() => openDialog('files',row)}>{copy.files}</button>}
        {canWrite && row.can_edit && <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
          onClick={() => openDialog('edit',row)}>{t('edit.edit')}</button>}
        {canWrite && row.can_undo && <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
          onClick={() => act('undo',row,position)}>{copy.undo}</button>}
        {canWrite && row.can_delete && <button type="button" className="btn btn-ghost btn-sm danger" disabled={busy}
          onClick={() => act('delete',row,position)}>{copy.deletePeriod}</button>}
      </div>
    </div>}
  </div>
}

function DisposalPeriod({ row, refs, expanded, onToggle, undo, canWrite, busy }) {
  const { t, lang, pick } = useI18n(), c = personnelText(lang), id = useId()
  const org = refName('org-units', row.org_unit_id, refs, pick)
  return <div className={row.is_current ? 'career-period career-current' : 'career-period'}>
    <button type="button" className="career-period-toggle" aria-expanded={expanded} aria-controls={expanded ? id : undefined} onClick={onToggle}>
      <span className="career-period-identity"><strong>{c.disposal}</strong>{org && <span>{c.origin} · {org}</span>}</span>
      <span className="career-period-dates">{row.date_to ? dateLabel(row.date_from) + ' – ' + dateLabel(row.date_to) : c.since + ' ' + dateLabel(row.date_from)}
        {' · '}{dayCount(row.days, lang)}</span><span className="career-expand" aria-hidden="true">{expanded ? '▴' : '▾'}</span>
    </button>
    {expanded && <div id={id} className="career-period-detail">
      <p className="page-hint">{c.tenureNote}</p>
      {row.reason && <p>{t('appointment.reason')} · {row.reason}</p>}
      {canWrite && row.can_undo && <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => undo(row)}>{c.undo}</button>}
    </div>}
  </div>
}

export default function CareerTab({ detail, ref_: refs, onChanged, readOnly }) {
  const { t, pick, lang } = useI18n(), copy = careerText(lang)
  const c = personnelText(lang)
  const [revision, setRevision] = useState(0)
  const facts = useCareerFacts(detail.id, revision)
  const { current, history, ambiguous, conflict } = careerTimeline(detail, facts?.summary?.as_of || localToday())
  const disposal = facts?.summary?.disposal && facts.disposals.find(row => row.is_current)
  const timeline = [
    ...history,
    ...(disposal && current ? [current] : []),
    ...(facts?.disposals || []).filter(row => row !== disposal).map(row => ({ ...row, is_current: false, is_disposal: true })),
  ].sort((a,b) => String(b.date_from).localeCompare(String(a.date_from)) || b.id - a.id)
  const cardPost = [refName('positions', detail.current_position_id, refs, pick),
    refName('org-units', detail.current_org_unit_id, refs, pick)].filter(Boolean).join(' · ')
  const cardAlreadyListed = history.some(row => row.is_internal
    && (!detail.current_position_id || row.position_id === detail.current_position_id)
    && (!detail.current_org_unit_id || row.org_unit_id === detail.current_org_unit_id))
  const [expanded, setExpanded] = useState(null), [modal, setModal] = useState(null)
  const [error, setError] = useState(null), [notice, setNotice] = useState(false), [busy, setBusy] = useState(false)
  const [filesChanged, setFilesChanged] = useState(false)
  const canWrite = !readOnly && detail.profile_status !== 'archived'
  const openDialog = (kind, row = null) => { setError(null); setNotice(false); setFilesChanged(false); setModal({ kind, row }) }
  const close = () => {
    setModal(null); setError(null)
    if (filesChanged) { setFilesChanged(false); onChanged?.() }
  }
  const saved = () => { close(); setNotice(true); setRevision(n => n + 1); onChanged?.() }
  const act = async (kind, row, position) => {
    const prompt = kind === 'disposal' ? c.undoQuestion.replace('{date}',dateLabel(row.date_from)) :
      kind === 'record' ? c.deleteQuestion.replace('{date}',dateLabel(row.event_date)) :
      kind === 'undo' ? copy.undoQuestion : copy.deleteQuestion
    if (busy || !window.confirm(prompt.replace('{name}',position))) return
    setBusy(true); setError(null); setNotice(false)
    try {
      if (kind === 'undo') await api.appointmentUndo(detail.id,row.id)
      else if (kind === 'disposal') await personnelApi.undoDisposal(detail.id, row.id)
      else if (kind === 'record') await personnelApi.remove(detail.id, row)
      else await api.delCareer(row.id)
      setExpanded(null); saved()
    } catch (exception) {
      setError(errorMessage(exception))
      if (exception.response?.status === 409) setRevision(n => n + 1)
    } finally { setBusy(false) }
  }
  const rowView = (row, isCurrent = false) => <CareerPeriod key={row.id} row={row} refs={refs} current={isCurrent} appointment={facts?.summary?.appointment}
    expanded={expanded === row.id} onToggle={() => setExpanded(id => id === row.id ? null : row.id)}
    openDialog={openDialog} act={act} canWrite={canWrite} busy={busy} />
  const disposalView = row => {
    const key = 'disposal-' + row.id
    return <DisposalPeriod key={key} row={row} refs={refs} expanded={expanded === key}
      onToggle={() => setExpanded(id => id === key ? null : key)} undo={r => act('disposal', r, c.disposal)} canWrite={canWrite} busy={busy} />
  }
  const titles = { record: modal?.row ? c.edit : c.add, appointment:t('appointment.add'), add:copy.addPeriod, edit:copy.editPeriod, files:copy.files }
  const scope = modal?.kind === 'record' ? personnelScope : modal?.kind === 'appointment' ? appointmentScope : modal?.kind === 'files'
    ? `${CANDIDATE_SCOPE}:attachment-work_experience:${modal.row.id}` : periodScope
  function requestClose(event) {
    event.preventDefault()
    if (!busy && confirmUnsavedLeave(scope)) close()
  }
  return <section className="career-workspace">
    <section className="card career-summary" aria-label={disposal ? c.current : copy.current}>
      <header className="career-heading"><h3>{disposal ? c.current : copy.current}</h3><div className="btn-row">
        {canWrite && detail.employment_status === 'active' && <button className="btn btn-sm" type="button" disabled={busy}
          onClick={() => openDialog('appointment')}>{t('appointment.add')}</button>}
        {canWrite && <button className="btn btn-ghost btn-sm" type="button" disabled={busy}
          onClick={() => openDialog('add')}>{copy.addPeriod}</button>}
      </div></header>
      {disposal ? disposalView(disposal) : current ? rowView(current, true) : <div className="career-no-current">
        <p>{conflict ? copy.conflict : ambiguous ? copy.ambiguous : history.length || cardPost ? copy.noCurrent : copy.empty}</p>
        {cardPost && !cardAlreadyListed && <small>{copy.cardPost}: {cardPost}</small>}
      </div>}
    </section>
    {notice && <p role="status" className="career-notice">{copy.success}</p>}
    {error && !modal && <p role="alert" className="alert alert-bad">{error}</p>}
    <PersonnelFacts snapshot={facts} canWrite={canWrite} busy={busy} openDialog={openDialog}
      remove={r => act('record', r, r.title || c[r.kind])} retry={() => setRevision(n => n + 1)} />
    {timeline.length > 0 && <section className="card career-history" aria-label={copy.history}>
      <header className="career-heading"><h3>{copy.history}</h3><span className="badge badge-mute">{timeline.length}</span></header>
      {timeline.map(row => row.is_disposal ? disposalView(row) : rowView(row))}
    </section>}
    {modal && <CareerDialog title={titles[modal.kind]} busy={busy} requestClose={requestClose} error={error}>
      {modal.kind === 'appointment' && <>
        <AppointmentForm employeeId={detail.id} positions={refs.positions} orgUnits={refs['org-units']}
          onBusy={setBusy} onError={setError} onSaved={saved} onCancel={requestClose} />
      </>}
      {(modal.kind === 'add' || modal.kind === 'edit') && <PeriodForm employeeId={detail.id} row={modal.row}
        refs={refs} onBusy={setBusy} busy={busy} onError={setError} onSaved={saved} onCancel={requestClose} />}
      {modal.kind === 'record' && <PersonnelForm employeeId={detail.id} record={modal.row} busy={busy} onConflict={() => setRevision(n => n + 1)}
        onBusy={setBusy} onError={setError} onSaved={saved} onCancel={requestClose} />}
      {modal.kind === 'files' && <Attachments entityType="work_experience" entityId={modal.row.id} readOnly={!canWrite}
        compact onError={setError} onBusy={setBusy} onChanged={() => setFilesChanged(true)} />}
    </CareerDialog>}
  </section>
}
