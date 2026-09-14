import React, { useState } from 'react'
import { useAuth } from '../auth'
import { useI18n, LANGUAGES } from '../i18n'
import { errorMessage } from '../api'

export default function LoginPage() {
  const { login } = useAuth()
  const { t, lang, setLang } = useI18n()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (ev) => {
    ev.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(username.trim(), password)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const fill = (u, p) => { setUsername(u); setPassword(p); setError(null) }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center',
                  background: 'var(--slate-100)', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
          <div className="lang-switch">
            {LANGUAGES.map((l) => (
              <button key={l.code}
                      className={`lang-btn ${lang === l.code ? 'active' : ''}`}
                      onClick={() => setLang(l.code)}>{l.short}</button>
            ))}
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12,
                        marginBottom: 20 }}>
            <span className="brand-mark">HR</span>
            <div>
              <div className="brand-title">{t('app.title')}</div>
              <div className="brand-sub">{t('app.subtitle')}</div>
            </div>
          </div>

          {error && <div className="alert alert-bad">{error}</div>}

          <form onSubmit={submit}>
            <div className="field">
              <label>{t('auth.username')}</label>
              <input value={username} autoFocus autoComplete="username"
                     onChange={(e) => setUsername(e.target.value)} required />
            </div>
            <div className="field">
              <label>{t('auth.password')}</label>
              <input type="password" value={password} autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <button className="btn" type="submit" disabled={busy}
                    style={{ width: '100%' }}>
              {busy ? t('common.loading') : t('auth.signIn')}
            </button>
          </form>
        </div>

        <div className="card">
          <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
            {t('auth.demoHint')}
          </div>
          <div className="btn-row">
            <button className="btn btn-ghost btn-sm"
                    onClick={() => fill('admin', 'admin')}>
              admin / admin — {t('auth.roles.admin')}
            </button>
            <button className="btn btn-ghost btn-sm"
                    onClick={() => fill('user', 'user')}>
              user / user — {t('auth.roles.viewer')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
