import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { personnelApi } from '../personnelApi'
import { personnelText, dayCount } from '../i18n/personnel'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import AppointmentForm, { appointmentScope } from './AppointmentForm'
import { confirmUnsavedLeave } from '../unsavedChanges'


/**
 * The employee's career transitions, and the form that records a new one.
 *
 * Recording an appointment closes the current posting and opens the new one,
 * so the move shows up in the CV and every tenure figure is recomputed from
 * the corrected intervals.
 */
export default function AppointmentPanel({ employeeId, positions, orgUnits,
                                           readOnly, onChanged, onError }) {
  const { t, pick, lang } = useI18n()
  const copy = personnelText(lang)
  const { isAdmin } = useAuth()
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)
  const load = useCallback(() => {
    if (!employeeId) return
    Promise.all([api.appointments(employeeId), personnelApi.disposals(employeeId)])
      .then(([work, disposals]) => setRows([...work.data.data, ...disposals.data.data.map(row => ({ ...row, is_disposal: true }))]
        .sort((a,b) => String(b.date_from).localeCompare(String(a.date_from)) || b.id - a.id)))
      .catch((e) => onError?.(errorMessage(e)))
  }, [employeeId, onError])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!saved) return
    const timer = setTimeout(() => setSaved(false), 3000)
    return () => clearTimeout(timer)
  }, [saved])

  const undo = async (row) => {
    if (!window.confirm(t('appointment.undoWarn'))) return
    onError?.(null)
    try {
      if (row.is_disposal) await personnelApi.undoDisposal(employeeId, row.id)
      else await api.appointmentUndo(employeeId, row.id)
      setSaved(true)
      load()
      onChanged?.()
    } catch (e) {
      onError?.(errorMessage(e))
    }
  }

  return (
    <>
      <div className="card flush">
        <div style={{ padding: '11px 14px',
                      borderBottom: '1px solid var(--slate-200)',
                      display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 13 }}>{t('appointment.title')}</strong>
          <div className="btn-row">
            {saved && <span className="badge badge-ok">{t('common.saved')}</span>}
            {!readOnly && (
              <button className="btn btn-sm" onClick={() => { if (!open || confirmUnsavedLeave(appointmentScope)) setOpen(!open) }}>
                {open ? t('common.cancel') : t('appointment.add')}
              </button>
            )}
          </div>
        </div>

        <table>
          <thead><tr>
            <th className="col-shrink">{t('employee.career.dateFrom')}</th>
            <th className="col-shrink">{t('employee.career.position')}</th>
            <th className="col-shrink">{t('employee.career.orgUnit')}</th>
            <th className="col-shrink">{t('appointment.type')}</th>
            <th className="col-grow">{t('appointment.basis')}</th>
            {!readOnly && isAdmin && <th style={{ width: 110 }} />}
          </tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={!readOnly && isAdmin ? 6 : 5} className="empty">
                {t('common.none')}
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={(r.is_disposal ? 'disposal-' : 'work-') + r.id}>
                <td className="mono" style={{ whiteSpace: 'nowrap' }}>
                  {r.date_from} – {r.date_to || '…'}
                  {r.is_current && (
                    <div><span className="badge badge-ok">
                      {t('appointment.current')}</span></div>
                  )}
                </td>
                <td>{r.is_disposal ? copy.disposal : r.position || '—'}</td>
                <td className="muted">{r.is_disposal ? pick(orgUnits.find(unit => unit.id === r.org_unit_id)) || '—' : r.org_unit || '—'}</td>
                <td>
                  <span className="badge badge-mute">
                    {r.is_disposal ? t('appointment.types.disposal') : r.is_appointment ? t('appointment.types.appointment') : copy.manual}
                  </span>
                </td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {r.is_disposal ? [dayCount(r.days, lang), r.reason].filter(Boolean).join(' · ') : r.source_vacancy
                    ? `${t('appointment.byVacancy')}: ${r.source_vacancy}`
                    : '—'}
                </td>
                {!readOnly && isAdmin && (
                  <td>
                    {r.can_undo && (
                      <button className="btn btn-ghost btn-sm"
                              onClick={() => undo(r)}>
                        {t('appointment.undo')}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!readOnly && open && (
        <div className="card">
          <h3>{t('appointment.add')}</h3>
          <AppointmentForm employeeId={employeeId} positions={positions} orgUnits={orgUnits} onError={onError}
            onSaved={() => { setOpen(false); setSaved(true); load(); onChanged?.() }} />
        </div>
      )}
    </>
  )
}
