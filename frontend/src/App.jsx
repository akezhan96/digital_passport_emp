import React, { useEffect, useState } from 'react'
import { I18nProvider, useI18n, LANGUAGES } from './i18n'
import { AuthProvider, useAuth } from './auth'
import { ThemeProvider, ThemeSwitch } from './theme'
import { renderDemo } from './renderDemo'
import { DemoAssistant, DemoBanner } from './components/DemoNotice'
import Dashboard from './pages/Dashboard'
import EmployeesPage from './pages/EmployeesPage'
import StructurePage from './pages/StructurePage'
import VacanciesPage from './pages/VacanciesPage'
import MatchingPage from './pages/MatchingPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AssistantPage from './pages/AssistantPage'
import MethodologyPage from './pages/MethodologyPage'
import CatalogsPage from './pages/CatalogsPage'
import AuditPage from './pages/AuditPage'
import LoginPage from './pages/LoginPage'
import ErrorBoundary from './components/ErrorBoundary'
import Icon from './components/Icon'
import { confirmUnsavedLeave, installGuardedHashNavigation } from './unsavedChanges'
import { resolveAppRoute, routeMountKey } from './appRoute'
import './App.css'
import './workspace.css'
import './statuses.css'

const PAGES = { dashboard: Dashboard, employees: EmployeesPage, structure: StructurePage,
  vacancies: VacanciesPage, matching: MatchingPage, analytics: AnalyticsPage,
  assistant: renderDemo ? DemoAssistant : AssistantPage, methodology: MethodologyPage, catalogs: CatalogsPage, audit: AuditPage }
const GROUPS = [ ['work', ['employees', 'structure', 'vacancies', 'matching']],
  ['analysis', ['assistant', 'analytics']], ['settings', ['catalogs', 'methodology', 'audit']] ]
const route = () => resolveAppRoute(location.hash, PAGES)

function Shell() {
  const { t, lang, setLang } = useI18n()
  const { user, isAdmin, logout } = useAuth()
  const [routeKey, setRouteKey] = useState(route)
  const page = routeKey.split('?')[0]
  const fullChat = page === 'assistant' && !renderDemo
  const [assistantCount, setAssistantCount] = useState(0)
  useEffect(() => installGuardedHashNavigation({ target: window, resolvePage: route,
    initialPage: route(), commitPage: setRouteKey }), [])
  // All route changes pass through the hash handler, including browser history.
  const navigate = key => { location.hash = `/${key}` }
  const Active = PAGES[page] || Dashboard
  const title = key => key === 'assistant' ? t('assistant.nav') : t(`nav.${key}`)
  const navButton = key => <div className="nav-entry" key={key}><a href={`#/${key}`} className={`nav-item ${page === key ? 'active' : ''}`}
    aria-current={page === key ? 'page' : undefined}>
    <Icon name={key} /><span>{title(key)}</span>{key === 'assistant' && assistantCount > 0 && <span className="nav-count">{assistantCount}</span>}</a>
    <a className="nav-new-window" href={`#/${key}`} target="_blank" rel="noopener noreferrer"
      title={`${t('workspace.newWindow')}: ${title(key)}`} aria-label={`${t('workspace.newWindow')}: ${title(key)}`}>↗</a></div>
  return <div className={`app workspace-app${fullChat ? ' workspace-app--assistant' : ''}`}>
    <a className="skip-link" href="#main-content" onClick={event => {
      event.preventDefault(); document.getElementById('main-content')?.focus()
    }}>{t('workspace.quick')}</a>
    <aside className="workspace-sidebar">
      <div className="workspace-brand"><span className="brand-mark">{t('app.mark')}</span>
        <strong>{t('app.title')}</strong></div>
      <nav aria-label={t('workspace.work')}>
        {navButton('dashboard')}
        {GROUPS.map(([group, keys]) => <div className="nav-group" key={group}>
          <div className="nav-group-label">{t(`workspace.${group}`)}</div>
          {keys.filter(key => key !== 'audit' || isAdmin).map(navButton)}
        </div>)}
      </nav>
    </aside>
    <div className="workspace-main">
      <header className="workspace-topbar"><span className="breadcrumb">{t('app.title')} <span>/</span> <strong>{title(page)}</strong></span>
        <div className="topbar-controls"><div className="lang-switch" role="group" aria-label="Тіл / Язык">
          {LANGUAGES.map(l => <button key={l.code} className={`lang-btn ${lang === l.code ? 'active' : ''}`}
            onClick={() => setLang(l.code)} aria-pressed={lang === l.code}>{l.short}</button>)}</div>
          <ThemeSwitch /><div className="user-block"><strong>{user?.displayName || user?.username}</strong>
            <small>{t(`auth.roles.${user.role}`)}</small></div>
          <button className="btn btn-ghost btn-sm" onClick={() => { if (confirmUnsavedLeave()) logout() }}>{t('auth.signOut')}</button>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className={`content workspace-content${fullChat ? ' workspace-content--assistant' : ''}`}>
        {renderDemo && <DemoBanner />}
        {!renderDemo && <div className="assistant-panel" hidden={page !== 'assistant'}><ErrorBoundary><AssistantPage onActiveCount={setAssistantCount} /></ErrorBoundary></div>}
        {(renderDemo || page !== 'assistant') && <ErrorBoundary key={routeMountKey(routeKey)}><Active routeKey={routeKey} onNavigate={navigate} /></ErrorBoundary>}
      </main>
    </div>
  </div>
}
function Gate() { const { isAuthenticated, checking } = useAuth(); return checking ? <div className="spinner" /> : isAuthenticated ? <Shell /> : <LoginPage /> }
export default function App() { return <I18nProvider><ThemeProvider><AuthProvider><Gate /></AuthProvider></ThemeProvider></I18nProvider> }
