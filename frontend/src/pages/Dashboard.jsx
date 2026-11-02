import { renderDemo } from '../renderDemo'
import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import { dashboardDistribution } from '../dashboardCharts'
import { rankingText } from '../i18n/employeeRanking'
import '../dashboardCharts.css'

function ChartValue({ row, number }) {
  return <dd><strong>{number.format(row.count)}</strong><span>{number.format(row.percent)}%</span></dd>
}

function DashboardCharts({ employees, vacancies, t, lang }) {
  const profiles = dashboardDistribution(employees, ['verified', 'draft', 'in_review', 'archived'])
  const jobs = dashboardDistribution(vacancies, ['active', 'draft', 'closed'])
  const number = new Intl.NumberFormat(lang === 'kk' ? 'kk-KZ' : 'ru-RU', { maximumFractionDigits: 1 })
  const label = (kind, key) => t(key === 'other' ? 'dashboard.otherStatus' : `dashboard.${kind}.${key}`)
  return <div className="dashboard-charts">
    <section className="card dashboard-chart" aria-labelledby="dashboard-profiles-title">
      <div className="dashboard-chart-heading"><h3 id="dashboard-profiles-title">{t('dashboard.profilesChart')}</h3></div>
      <div className="dashboard-profile-chart">
        <div className="dashboard-donut">
          <svg viewBox="0 0 120 120" aria-hidden="true" focusable="false">
            <circle className="dashboard-donut-track" cx="60" cy="60" r="49" />
            {profiles.rows.filter(row => row.count > 0).map(row => <circle key={row.key}
              className={`dashboard-donut-segment dashboard-chart-color-${row.key}`} cx="60" cy="60" r="49"
              pathLength="100" strokeDasharray={`${row.percent} ${100 - row.percent}`}
              strokeDashoffset={-row.offset} transform="rotate(-90 60 60)" />)}
          </svg>
          <div className="dashboard-donut-centre"><strong>{number.format(profiles.total)}</strong><span>{t('dashboard.total')}</span></div>
        </div>
        <dl className="dashboard-chart-legend">{profiles.rows.map(row => <div key={row.key}>
          <dt><span className={`dashboard-chart-dot dashboard-chart-color-${row.key}`} aria-hidden="true" />{label('profileStatuses', row.key)}</dt>
          <ChartValue row={row} number={number} />
        </div>)}</dl>
      </div>
      {!profiles.total && <p className="dashboard-chart-empty">{t('dashboard.noProfiles')}</p>}
    </section>
    <section className="card dashboard-chart" aria-labelledby="dashboard-vacancies-title">
      <div className="dashboard-chart-heading"><h3 id="dashboard-vacancies-title">{t('dashboard.vacanciesChart')}</h3>
        <span className="dashboard-chart-total">{t('dashboard.total')}: {number.format(jobs.total)}</span></div>
      <div className="dashboard-vacancy-chart">{jobs.rows.map(row => <div key={row.key}>
        <dl className="dashboard-chart-legend"><div>
          <dt><span className={`dashboard-chart-dot dashboard-chart-color-${row.key}`} aria-hidden="true" />{label('vacancyStatuses', row.key)}</dt>
          <ChartValue row={row} number={number} />
        </div></dl>
        <div className="dashboard-bar-track" aria-hidden="true"><div className={`dashboard-bar-fill dashboard-chart-color-${row.key}`} style={{ width: `${row.percent}%` }} /></div>
      </div>)}</div>
      {!jobs.total && <p className="dashboard-chart-empty">{t('dashboard.noVacancies')}</p>}
    </section>
  </div>
}

export default function Dashboard({ onNavigate }) {
  const { isAdmin } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.dashboard().then(r => setData(r.data)).catch(e => setError(errorMessage(e))) }, [])
  if (error) return <div className="alert alert-bad">{error}</div>
  if (!data) return <div className="spinner" />
  return <DashboardContent data={data} isAdmin={isAdmin} onNavigate={onNavigate} />
}

export function DashboardContent({ data, isAdmin, onNavigate }) {
  const { t, labelCode, pick, lang } = useI18n()
  const [search, setSearch] = useState('')
  const e = data.employees
  const methodology = data.candidate_methodology
  const stats = [[e.total, 'dashboard.employeesTotal', 'employees'], [e.verified, 'dashboard.verified', 'shield'],
    [data.vacancies.active, 'dashboard.activeVacancies', 'vacancies'], [data.matching_runs, 'dashboard.matchingRuns', 'matching']]
  return <>
    <div className="page-heading"><div><p className="eyebrow">{t('workspace.overview')}</p><h1>{t('workspace.welcome')}</h1>
      <p className="page-hint">{t('workspace.intro')}</p></div></div>
    <div className="dashboard-columns">
      <section className="card action-card"><div className="section-heading"><h3>{t('workspace.quick')}</h3><Icon name="arrow" /></div>
        <form className="dashboard-search" onSubmit={event => { event.preventDefault(); onNavigate(`employees?search=${encodeURIComponent(search.trim())}`) }}>
          <label htmlFor="dashboard-search">{t('workspace.searchLabel')}</label>
          <div><input id="dashboard-search" type="search" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} placeholder={t('workspace.searchPlaceholder')} />
            <button className="btn" type="submit">{t('workspace.searchButton')}</button></div>
        </form>
        {isAdmin && <button className="quick-action" onClick={() => onNavigate('employees?create=1')}><span className="action-icon"><Icon name="employees" /></span><strong>{t('employee.add')}</strong><Icon name="arrow" size={17} /></button>}
        {[['employees', 'people'], ['assistant', 'ask'], ['vacancies', 'vacancy']].filter(([page]) => !renderDemo || page !== 'assistant').map(([page, label]) => <button className="quick-action" key={page} onClick={() => onNavigate(page)}>
          <span className="action-icon"><Icon name={page} /></span><strong>{t(`workspace.${label}`)}</strong><Icon name="arrow" size={17} /></button>)}
        <a className="quick-action" href="#/analytics?tab=ranking"><span className="action-icon"><Icon name="analytics" /></span>
          <strong>{rankingText(lang).title}</strong><Icon name="arrow" size={17} /></a>
      </section>
      <section className="card attention-card"><p className="eyebrow">{t('workspace.attention')}</p>
        <h3>{t(e.in_review ? 'workspace.review' : 'workspace.reviewEmpty')}</h3>
        {e.in_review > 0 && <a className="attention-value attention-count" href="#/employees?status=in_review" aria-label={`${t('workspace.reviewOpen')}: ${e.in_review}`}>{e.in_review}</a>}
        <p className="page-hint">{t(e.in_review ? 'workspace.reviewHint' : 'workspace.reviewEmptyHint')}</p>
        {e.in_review > 0 && <button className="btn btn-ghost" onClick={() => onNavigate('employees?status=in_review')}>{t('workspace.reviewOpen')} <Icon name="arrow" size={16} /></button>}
        <div className="dashboard-drafts"><span>{t('workspace.drafts')}: <strong>{e.draft}</strong></span>
          {e.draft > 0 && <a href="#/employees?status=draft">{t('workspace.draftsOpen')}</a>}</div>
      </section>
    </div>
    <div className="grid grid-4 summary-stats">{stats.map(([value, key, icon]) => <div className="card stat" key={key}>
      <div className="stat-top"><span>{t(key)}</span><Icon name={icon} /></div><div className="stat-value">{value}</div>
      {icon === 'shield' && <div className="stat-track"><span style={{ width: `${e.verified_percent}%` }} /></div>}
    </div>)}</div>
    <DashboardCharts employees={e} vacancies={data.vacancies} t={t} lang={lang} />
    <div className="grid grid-2">
      <section className="card"><h3>{t('dashboard.scoringModel')}</h3><div className="method-summary"><Icon name="methodology" size={32} />
        <div><strong>{pick(methodology) || t('common.none')}</strong><p className="muted">{t('methodology.version')} {methodology?.version || '—'} · {labelCode(methodology?.status)}</p></div></div>
        <button className="btn btn-ghost btn-sm" onClick={() => onNavigate('methodology')}>{t('nav.methodology')} <Icon name="arrow" size={16} /></button>
      </section>
      {isAdmin && <section className="card"><h3>{t('dashboard.recentActivity')}</h3>
        {!data.recent_activity.length ? <div className="empty">{t('common.none')}</div> : <div className="activity-list">
          {data.recent_activity.slice(0, 5).map((row, i) => <div className="activity-row" key={i}><span className="activity-dot" />
            <div><strong>{labelCode(row.action)}</strong><small>{labelCode(row.entity_type)} · {row.changed_by}</small></div>
            <time>{row.changed_at?.slice(11, 16)}</time></div>)}</div>}
      </section>}
    </div>
  </>
}
