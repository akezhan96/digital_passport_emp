import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useFormChanges } from '../useFormChanges'
import { localToday, personnelText } from '../i18n/personnel'
import { CANDIDATE_SCOPE } from '../unsavedChanges'

export const appointmentScope = `${CANDIDATE_SCOPE}:appointment`
const TYPES = ['appointment', 'disposal']

export default function AppointmentForm({ employeeId, positions = [], orgUnits = [], onSaved, onError, onBusy, onCancel }) {
  const { t, pick, lang } = useI18n()
  const [form, setForm] = useState({ org_unit_id: '', position_id: '', effective_date: '', appointment_type: 'appointment', reason: '' })
  const disposal = form.appointment_type === 'disposal'
  const [staffing, setStaffing] = useState(null)
  const [pending, setPending] = useState(false)
  const [retry, setRetry] = useState(0)
  const accept = useFormChanges(form, { scope: appointmentScope })
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }))
  useEffect(() => {
    if (disposal || !form.org_unit_id) return
    const unit = form.org_unit_id
    let active = true
    api.unitStaffing(Number(unit))
      .then(({ data }) => { if (active) setStaffing({ unit, data }) })
      .catch(error => { if (active) setStaffing({ unit, error: errorMessage(error) }) })
    return () => { active = false }
  }, [form.org_unit_id, disposal, retry])
  const selected = staffing?.unit === form.org_unit_id ? staffing : null
  const lines = selected?.data?.lines
  const options = lines?.length ? lines.filter(line => line.is_active && (line.vacant > 0
    || ((line.holders || []).some(person => person.id === employeeId) && line.occupied <= line.headcount))).map(line => ({
    id: line.position_id, label: line[`position_${lang}`] || line.position_ru,
  })) : positions.map(position => ({ id: position.id, label: pick(position) }))
  const submit = async event => {
    event.preventDefault()
    if (pending || (!disposal && (!selected?.data || !form.position_id))) return
    setPending(true); onBusy?.(true); onError?.(null)
    try {
      const body = { appointment_type: form.appointment_type, effective_date: form.effective_date, reason: form.reason.trim() || null }
      if (!disposal) Object.assign(body, { org_unit_id: Number(form.org_unit_id), position_id: Number(form.position_id) })
      await api.appointmentCreate(employeeId, body)
      accept(); onSaved()
    } catch (error) { onError?.(errorMessage(error)) }
    finally { setPending(false); onBusy?.(false) }
  }
  return <form onSubmit={submit}>
    <fieldset disabled={pending} className="career-form-fields">
      <label className="field">{t('appointment.type')}<select aria-label={t('appointment.type')} value={form.appointment_type} onChange={e => change('appointment_type', e.target.value)}>
        {TYPES.map(key => <option key={key} value={key}>{t(`appointment.types.${key}`)}</option>)}</select></label>
      {disposal && <p className="page-hint">{personnelText(lang).disposalHint}</p>}
      {!disposal && <><div className="form-row">
        <label className="field">{t('appointment.orgUnit')}<select required value={form.org_unit_id}
          onChange={e => setForm(old => ({ ...old, org_unit_id: e.target.value, position_id: '' }))}>
          <option value="">—</option>{orgUnits.map(row => <option key={row.id} value={row.id}>{pick(row)}</option>)}
        </select></label>
        <label className="field">{t('appointment.position')}<select required value={form.position_id}
          disabled={!selected?.data} onChange={e => change('position_id', e.target.value)}>
          <option value="">—</option>{selected?.data && options.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}
        </select></label>
      </div>
      {selected?.error && <div className="alert alert-bad" role="alert">{selected.error}{' '}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setStaffing(null); setRetry(n => n + 1) }}>{t('errors.retry')}</button></div>}
      {lines?.length > 0 && options.length === 0 && <p role="status">{t('staffing.fullyStaffed')}</p>}</>}
      <div className="form-row">
        <label className="field">{t('appointment.effectiveDate')}<input type="date" required max={localToday()} value={form.effective_date}
          onChange={e => change('effective_date', e.target.value)} /></label>

      </div>
      <label className="field">{t('appointment.reason')}<input value={form.reason} onChange={e => change('reason', e.target.value)} /></label>
      <div className="btn-row"><button type="submit" className="btn" disabled={!disposal && (!selected?.data || !form.position_id)}>{t('common.save')}</button>
        {onCancel && <button type="button" className="btn btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>}</div>
    </fieldset>
  </form>
}
