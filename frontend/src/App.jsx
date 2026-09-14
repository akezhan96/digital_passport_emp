import React, { useState } from 'react'
import { I18nProvider, useI18n, LANGUAGES } from './i18n'
import { AuthProvider, useAuth } from './auth'
import Dashboard from './pages/Dashboard'
import EmployeesPage from './pages/EmployeesPage'
import VacanciesPage from './pages/VacanciesPage'
import MatchingPage from './pages/MatchingPage'
import MethodologyPage from './pages/MethodologyPage'
import CatalogsPage from './pages/CatalogsPage'
import AuditPage from './pages/AuditPage'
import LoginPage from './pages/LoginPage'
import ErrorBoundary from './components/ErrorBoundary'
import './App.css'

// adminOnly pages are hidden from viewers here AND refused by the API, so the
// UI gate is convenience, not the security boundary.
const PAGES = [
  { key: 'dashboard',   Component: Dashboard },
  { key: 'employees',   Component: EmployeesPage },
  { key: 'vacancies',   Component: VacanciesPage },
  { key: 'matching',    Component: MatchingPage },
  { key: 'methodology', Component: MethodologyPage, adminOnly: true },
  { key: 'catalogs',    Component: CatalogsPage,    adminOnly: true },
  { key: 'audit',       Component: AuditPage,       adminOnly: true },
]

function Shell() {
  const { t, lang, setLang } = useI18n()
  const { user, isAdmin, logout } = useAuth()
  const [page, setPage] = useState('dashboard')

  const visible = PAGES.filter((p) => isAdmin || !p.adminOnly)
  const current = visible.find((p) => p.key === page) || visible[0]
  const Active = current.Component

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">HR</span>
          <div>
            <div className="brand-title">{t('app.title')}</div>
            <div className="brand-sub">{t('app.subtitle')}</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ textAlign: 'right', lineHeight: 1.3 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>
              {user?.displayName || user?.username}
            </div>
            <span className={`badge ${isAdmin ? 'badge-conf' : 'badge-mute'}`}>
              {t(`auth.roles.${isAdmin ? 'admin' : 'viewer'}`)}
            </span>
          </div>

          <div className="lang-switch" role="group" aria-label="Language">
            {LANGUAGES.map((l) => (
              <button key={l.code}
                      className={`lang-btn ${lang === l.code ? 'active' : ''}`}
                      onClick={() => setLang(l.code)} title={l.label}>
                {l.short}
              </button>
            ))}
          </div>

          <button className="btn btn-ghost btn-sm" onClick={logout}>
            {t('auth.signOut')}
          </button>
        </div>
      </header>

      <div className="body">
        <nav className="sidebar">
          {visible.map((p) => (
            <button key={p.key}
                    className={`nav-item ${current.key === p.key ? 'active' : ''}`}
                    onClick={() => setPage(p.key)}>
              {t(`nav.${p.key}`)}
            </button>
          ))}

          {!isAdmin && (
            <div className="muted" style={{ fontSize: 11, padding: '14px 12px',
                                            lineHeight: 1.5 }}>
              {t('auth.viewerNotice')}
            </div>
          )}
        </nav>

        <main className="content">
          {/* Keyed by page so switching tabs clears a previous crash. */}
          <ErrorBoundary key={current.key}>
            <Active />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

function Gate() {
  const { isAuthenticated, checking } = useAuth()
  if (checking) return <div className="spinner" style={{ marginTop: 120 }} />
  return isAuthenticated ? <Shell /> : <LoginPage />
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </I18nProvider>
  )
}
