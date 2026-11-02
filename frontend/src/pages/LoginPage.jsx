import { renderDemo } from '../renderDemo'
import { DemoBanner } from '../components/DemoNotice'
import React, { useState } from 'react'
import { useAuth } from '../auth'
import { useI18n, LANGUAGES } from '../i18n'
import { errorMessage } from '../api'
import { ThemeSwitch } from '../theme'

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

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center',
                  background: 'var(--slate-100)', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 10,
                      marginBottom: 18 }}>
          <div className="lang-switch">
            {LANGUAGES.map((l) => (
              <button key={l.code}
                      className={`lang-btn ${lang === l.code ? 'active' : ''}`}
                      onClick={() => setLang(l.code)}>{l.short}</button>
            ))}
          </div>
          <ThemeSwitch />
        </div>

        {renderDemo && <DemoBanner />}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12,
                        marginBottom: 20 }}>
            <span className="brand-mark">{t('app.mark')}</span>
            <div className="brand-title">{t('app.title')}</div>
          </div>

          {error && <div className="alert alert-bad">{error}</div>}

          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="login-username">{t('auth.username')}</label>
              <input id="login-username" value={username} autoFocus autoComplete="username"
                     onChange={(e) => setUsername(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="login-password">{t('auth.password')}</label>
              <input id="login-password" type="password" value={password} autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <button className="btn" type="submit" disabled={busy}
                    style={{ width: '100%' }}>
              {busy ? t('common.loading') : t('auth.signIn')}
            </button>
          </form>
        </div>

      </div>
    </div>
  )
}
