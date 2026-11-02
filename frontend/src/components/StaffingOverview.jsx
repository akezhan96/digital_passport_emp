import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

/**
 * The establishment across the whole company, and every free post in it.
 *
 * This is the view HR plans hiring from: which units are fully staffed, which
 * are carrying vacancies, and exactly which posts those vacancies are.
 */
export default function StaffingOverview({ onError, onOpenUnit }) {
  const { t, pick, lang } = useI18n()
  const [summary, setSummary] = useState(null)
  const [vacant, setVacant] = useState(null)
  const [view, setView] = useState('units')

  useEffect(() => {
    api.staffingSummary().then((r) => setSummary(r.data))
      .catch((e) => onError(errorMessage(e)))
    api.staffingVacant().then((r) => setVacant(r.data))
      .catch((e) => onError(errorMessage(e)))
  }, [onError])

  if (!summary) return <div className="spinner" />

  const { totals } = summary
  const percent = totals.established
    ? Math.round((totals.occupied / totals.established) * 100) : 0

  return (
    <>
      <div className="grid grid-4">
        <div className="card stat">
          <div className="stat-value">{totals.established}</div>
          <div className="stat-label">{t('staffing.established')}</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{totals.occupied}</div>
          <div className="stat-label">
            {t('staffing.occupied')} <span className="muted">· {percent}%</span>
          </div>
        </div>
        <div className="card stat">
          <div className="stat-value" style={{ color: 'var(--accent)' }}>
            {totals.vacant}
          </div>
          <div className="stat-label">{t('staffing.vacant')}</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{totals.lines}</div>
          <div className="stat-label">{t('staffing.lines')}</div>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${view === 'units' ? 'active' : ''}`}
                onClick={() => setView('units')}>{t('staffing.overview')}</button>
        <button className={`tab ${view === 'vacant' ? 'active' : ''}`}
                onClick={() => setView('vacant')}>
          {t('staffing.vacantPosts')}
          {vacant && <span className="muted"> · {vacant.count}</span>}
        </button>
      </div>

      {view === 'units' ? (
        <div className="card flush">
          <table>
            <thead><tr>
              <th className="col-grow">{t('employee.orgUnit')}</th>
              <th className="col-shrink">{t('employee.career.unitType')}</th>
              <th className="col-shrink num">{t('staffing.established')}</th>
              <th className="col-shrink num">{t('staffing.occupied')}</th>
              <th className="col-shrink num">{t('staffing.vacant')}</th>
              <th style={{ width: 170 }}>{t('staffing.filled')}</th>
            </tr></thead>
            <tbody>
              {summary.data.map((row) => {
                const pct = row.established
                  ? Math.round((row.occupied / row.established) * 100) : 0
                return (
                  <tr key={row.org_unit_id}>
                    <td>
                      <button className="btn btn-ghost btn-sm"
                              style={{ border: 0, background: 'transparent',
                                       padding: 0, fontWeight: 600 }}
                              onClick={() => onOpenUnit?.(row.org_unit_id)}>
                        {pick(row)}
                      </button>
                      <div className="muted mono" style={{ fontSize: 11 }}>
                        {row.code}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-mute">
                        {row.unit_type || '—'}
                      </span>
                    </td>
                    <td className="num"><strong>{row.established}</strong></td>
                    <td className="num">{row.occupied}</td>
                    <td className="num">
                      {row.vacant > 0
                        ? <span className="badge badge-ok">{row.vacant}</span>
                        : <span className="muted">0</span>}
                      {row.over_established > 0 && (
                        <span className="badge badge-warn"
                              style={{ marginLeft: 4 }}
                              title={t('staffing.overEstablished')}>
                          +{row.over_established}
                        </span>
                      )}
                    </td>
                    <td>
                      {row.established === 0 ? (
                        <span className="muted" style={{ fontSize: 11.5 }}>—</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center',
                                      gap: 8 }}>
                          <div style={{ flex: 1, height: 5, borderRadius: 3,
                                        background: 'var(--slate-200)',
                                        overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${pct}%`,
                                          background: 'var(--accent)' }} />
                          </div>
                          <span className="muted mono" style={{ fontSize: 11 }}>
                            {pct}%
                          </span>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <p className="page-hint">{t('staffing.vacantPostsHint')}</p>
          {!vacant ? <div className="spinner" /> : (
            <div className="card flush">
              {vacant.data.length === 0 ? (
                <div className="empty">{t('staffing.fullyStaffed')}</div>
              ) : (
                <table>
                  <thead><tr>
                    <th className="col-grow">{t('employee.orgUnit')}</th>
                    <th className="col-shrink">{t('staffing.position')}</th>
                    <th className="col-shrink">{t('staffing.grade')}</th>
                    <th className="col-shrink num">{t('staffing.vacant')}</th>
                    <th className="col-shrink num">{t('staffing.headcount')}</th>
                  </tr></thead>
                  <tbody>
                    {vacant.data.map((row) => (
                      <tr key={row.staffing_id}>
                        <td>
                          <button className="btn btn-ghost btn-sm"
                                  style={{ border: 0, background: 'transparent',
                                           padding: 0, fontWeight: 600 }}
                                  onClick={() => onOpenUnit?.(row.org_unit_id)}>
                            {row[`org_unit_${lang}`] || row.org_unit_ru}
                          </button>
                        </td>
                        <td>{row[`position_${lang}`] || row.position_ru}</td>
                        <td className="muted">{row.grade || '—'}</td>
                        <td className="num">
                          <span className="badge badge-ok">{row.vacant}</span>
                        </td>
                        <td className="num muted">{row.headcount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}
    </>
  )
}
