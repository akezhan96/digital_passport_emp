import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

export default function Dashboard() {
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.dashboard().then((r) => setData(r.data)).catch((e) => setError(errorMessage(e)))
  }, [])

  if (error) return <div className="alert alert-bad">{error}</div>
  if (!data) return <div className="spinner" />

  const e = data.employees

  return (
    <>
      <h2>{t('dashboard.title')}</h2>
      <p className="page-hint">{t('dashboard.principle')}</p>

      <div className="grid grid-4">
        <div className="card stat">
          <div className="stat-value">{e.total}</div>
          <div className="stat-label">{t('dashboard.employeesTotal')}</div>
        </div>
        <div className="card stat">
          <div className="stat-value" style={{ color: 'var(--ok)' }}>{e.verified}</div>
          <div className="stat-label">{t('dashboard.verified')} · {e.verified_percent}%</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.vacancies.active}</div>
          <div className="stat-label">{t('dashboard.activeVacancies')}</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.competencies}</div>
          <div className="stat-label">{t('dashboard.competencies')}</div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3>{t('dashboard.scoringModel')}</h3>
          {data.scoring_model.version ? (
            <table>
              <tbody>
                <tr>
                  <td className="muted">{t('methodology.version')}</td>
                  <td><strong>{data.scoring_model.version}</strong></td>
                </tr>
                <tr>
                  <td className="muted">{t('common.name')}</td>
                  <td>{data.scoring_model.name}</td>
                </tr>
                <tr>
                  <td className="muted">{t('common.status')}</td>
                  <td>
                    <span className="badge badge-ok">
                      {t(`methodology.modelStatus.${data.scoring_model.status}`)}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="muted">{t('dashboard.matchingRuns')}</td>
                  <td>{data.matching_runs}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <div className="empty">{t('common.none')}</div>
          )}
        </div>

        <div className="card">
          <h3>{t('dashboard.recentActivity')}</h3>
          {data.recent_activity.length === 0 ? (
            <div className="empty">{t('common.none')}</div>
          ) : (
            <table>
              <tbody>
                {data.recent_activity.map((row, i) => (
                  <tr key={i}>
                    <td><span className="badge badge-mute">{row.action}</span></td>
                    <td>{row.entity_type}</td>
                    <td className="muted">{row.changed_by}</td>
                    <td className="muted mono">
                      {row.changed_at ? row.changed_at.slice(0, 16).replace('T', ' ') : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
