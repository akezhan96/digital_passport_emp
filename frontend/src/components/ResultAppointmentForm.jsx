import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { recruitmentText } from '../i18n/recruitment'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { confirmUnsavedLeave } from '../unsavedChanges'

export default function ResultAppointmentForm({ result, onDone, onCancel }) {
  const { t, pick, lang } = useI18n()
  const c = recruitmentText(lang)
  const scope = `result-appointment-${result.id}`
  const [references, setReferences] = useState(null)
  const [referencesReload, setReferencesReload] = useState(0)
  const [staffing, setStaffing] = useState(null)
  const [staffingError, setStaffingError] = useState('')
  const [staffingReload, setStaffingReload] = useState(0)
  const [form, setForm] = useState({ org_unit_id: result.vacancy_org_unit_id || '', position_id: '',
    effective_date: '', appointment_type: 'appointment', reason: '' })
  const [confirmed, setConfirmed] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const markSaved = useUnsavedChanges(dirty, c.appointmentDirty, scope)
  useEffect(() => {
    let live = true
    setError('')
    Promise.all([api.refList('positions'), api.refList('org-units')]).then(([positions, units]) => {
      if (live) setReferences({ positions: positions.data.data, units: units.data.data })
    }).catch(e => { if (live) setError(errorMessage(e)) })
    return () => { live = false }
  }, [referencesReload])
  useEffect(() => {
    setStaffing(null); setStaffingError('')
    if (!form.org_unit_id) return
    let live = true
    api.unitStaffing(Number(form.org_unit_id)).then(r => { if (live) setStaffing(r.data) })
      .catch(e => { if (live) setStaffingError(errorMessage(e)) })
    return () => { live = false }
  }, [form.org_unit_id, staffingReload])
  const change = (key, value) => { setForm(old => ({ ...old, [key]: value, ...(key === 'org_unit_id' ? { position_id: '' } : {}) })); setDirty(true); setConfirmed(false) }
  const positions = !staffing?.lines?.length ? references?.positions || []
    : staffing.lines.filter(line => line.is_active && line.vacant > 0).map(line => ({ id: line.position_id, name_ru: line.position_ru, name_kk: line.position_kk }))
  const submit = async event => {
    event.preventDefault()
    if (!confirmed || busy || !staffing) return
    setBusy(true); setError('')
    try {
      await api.appointFromResult(result.id, { ...form, org_unit_id: Number(form.org_unit_id), position_id: Number(form.position_id), reason: form.reason.trim() })
      markSaved(); setDirty(false); onDone()
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  return <form className="card recruitment-appointment" onSubmit={submit} aria-label={c.appoint}>
    <h3>{c.appoint}</h3><p><strong>{result.display_name}</strong></p>
    <p className="muted">{c.appointmentEffect}</p>
    {error && <div className="alert alert-bad" role="alert">{error}</div>}
    {!references ? error ? <button type="button" className="btn btn-ghost" onClick={() => setReferencesReload(value => value + 1)}>{c.retry}</button> : <div className="spinner" /> : <>
      <div className="form-row"><div className="field"><label htmlFor="result-unit">{t('appointment.orgUnit')}</label>
        <select id="result-unit" required disabled={busy || Boolean(result.vacancy_org_unit_id)} value={form.org_unit_id} onChange={e => change('org_unit_id', e.target.value)}>
          <option value="">—</option>{references.units.map(unit => <option key={unit.id} value={unit.id}>{pick(unit)}</option>)}</select></div>
        <div className="field"><label htmlFor="result-position">{t('appointment.position')}</label>
          <select id="result-position" required disabled={busy || !staffing} value={form.position_id} onChange={e => change('position_id', e.target.value)}>
            <option value="">—</option>{positions.map(position => <option key={position.id} value={position.id}>{pick(position)}</option>)}</select></div></div>
      {form.org_unit_id && !staffing && !staffingError && <p role="status" className="muted">{c.loadingStaffing}</p>}
      {staffingError && <div className="alert alert-warn" role="alert">{c.staffingFailed} <button type="button" className="btn btn-ghost btn-sm" onClick={() => setStaffingReload(n => n + 1)}>{c.retry}</button></div>}
      {staffing?.lines?.length > 0 && !positions.length && <div className="alert alert-warn">{t('staffing.fullyStaffed')}</div>}
      <div className="form-row"><div className="field"><label htmlFor="result-date">{t('appointment.effectiveDate')}</label>
        <input id="result-date" type="date" required max={new Date().toISOString().slice(0, 10)} value={form.effective_date} disabled={busy} onChange={e => change('effective_date', e.target.value)} /></div>
      </div>
      <div className="field"><label htmlFor="result-appointment-reason">{c.appointmentBasis}</label><textarea id="result-appointment-reason" required maxLength={2000} value={form.reason} disabled={busy} onChange={e => change('reason', e.target.value)} /></div>
      <label className="checkbox"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => { setConfirmed(e.target.checked); setDirty(true) }} />{c.appointmentConfirm}</label>
    </>}
    <div className="btn-row" style={{ marginTop: 14 }}><button className="btn" disabled={busy || !confirmed || !staffing || !positions.length || !form.reason.trim()}>{busy ? c.saving : c.confirmAppointment}</button>
      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => { if (confirmUnsavedLeave(scope)) onCancel() }}>{t('common.cancel')}</button></div>
  </form>
}
