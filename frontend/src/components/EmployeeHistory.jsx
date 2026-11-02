import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

const ENTITY_LABEL = {
  employee: 'employee.tabs.general',
  employee_education: 'employee.tabs.education',
  employee_language: 'employee.tabs.languages',
  employee_training: 'employee.tabs.training',
  employee_work_experience: 'employee.tabs.career',
}

function Values({ values }) {
  const { t, labelCode } = useI18n()
  if (!values || Object.keys(values).length === 0) return <span>—</span>
  return (
    <div style={{ fontSize: 12 }}>
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <span className="mono muted">{labelCode(key)}:</span> {typeof value === 'boolean' ? t(value ? 'common.yes' : 'common.no')
            : key === 'personnel_kind' ? labelCode(value)
            : key === 'appointment_type' && value ? t(value === 'disposal' ? 'appointment.types.disposal' : 'appointment.types.appointment')
            : String(value ?? '—')}
        </div>
      ))}
    </div>
  )
}

/** Every recorded change to this employee, including their child records. */
export default function EmployeeHistory({ employeeId, refreshKey }) {
  const { t, labelCode } = useI18n()
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    if (!employeeId) return
    setBusy(true)
    api.employeeHistory(employeeId)
      .then((r) => setRows(r.data.data))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setBusy(false))
  }, [employeeId, refreshKey])

  if (error) return <div className="alert alert-bad">{error}</div>
  if (busy) return <div className="spinner" />

  return (
    <div className="card flush">
      <div style={{ padding: '11px 14px',
                    borderBottom: '1px solid var(--slate-200)',
                    fontWeight: 620, fontSize: 13 }}>
        {t('edit.history')} <span className="muted">({rows.length})</span>
      </div>

      {rows.length === 0 ? (
        <div className="empty">{t('edit.noHistory')}</div>
      ) : (
        <table>
          <thead><tr>
            <th>{t('audit.action')}</th>
            <th>{t('audit.entity')}</th>
            <th>{t('edit.was')}</th>
            <th>{t('edit.became')}</th>
            <th>{t('audit.reason')}</th>
            <th>{t('audit.user')}</th>
            <th>{t('audit.date')}</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><span className="badge badge-mute">{labelCode(r.action)}</span></td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {ENTITY_LABEL[r.entity_type]
                    ? t(ENTITY_LABEL[r.entity_type]) : labelCode(r.entity_type)}
                </td>
                <td><Values values={r.old_values} /></td>
                <td><Values values={r.new_values} /></td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {r.reason || '—'}
                </td>
                <td className="muted">{r.changed_by}</td>
                <td className="mono muted" style={{ fontSize: 11.5,
                                                    whiteSpace: 'nowrap' }}>
                  {r.changed_at ? r.changed_at.slice(0, 16).replace('T', ' ') : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
