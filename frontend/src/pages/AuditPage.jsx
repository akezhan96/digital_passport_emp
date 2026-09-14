import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

export default function AuditPage() {
  const { t } = useI18n()
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    api.auditLog({ entity_type: filter || undefined, limit: 200 })
      .then((r) => setRows(r.data.data))
      .catch((e) => setError(errorMessage(e)))
  }, [filter])

  return (
    <>
      <h2>{t('audit.title')}</h2>
      <p className="page-hint">{t('audit.hint')}</p>

      {error && <div className="alert alert-bad">{error}</div>}

      <div className="card">
        <div className="field" style={{ marginBottom: 0, maxWidth: 320 }}>
          <label>{t('audit.entity')}</label>
          <input value={filter} onChange={(e) => setFilter(e.target.value)}
                 placeholder="employee, vacancy, requirement, scoring_model…" />
        </div>
      </div>

      <div className="card flush">
        <table>
          <thead><tr>
            <th>{t('audit.action')}</th>
            <th>{t('audit.entity')}</th>
            <th>{t('audit.reason')}</th>
            <th>{t('audit.user')}</th>
            <th>{t('audit.date')}</th>
          </tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="empty">{t('common.none')}</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id}>
                <td><span className="badge badge-mute">{r.action}</span></td>
                <td>
                  {r.entity_type}
                  {r.entity_id != null && <span className="muted"> #{r.entity_id}</span>}
                </td>
                <td className="muted">{r.reason || '—'}</td>
                <td>{r.changed_by}</td>
                <td className="mono muted">
                  {r.changed_at ? r.changed_at.slice(0, 19).replace('T', ' ') : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
