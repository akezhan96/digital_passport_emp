import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { useI18n } from './i18n'

/**
 * Light, dark, or whatever the machine is set to.
 *
 * Three states rather than a switch: "system" is the sensible default and a
 * two-position toggle cannot express it. Someone who has set their laptop to
 * turn dark in the evening expects this page to do the same without being
 * asked, and someone who has deliberately chosen light expects that choice to
 * survive their laptop going dark. Only a third state satisfies both.
 *
 * The choice is written to the root element as `data-theme`, which is what the
 * stylesheet keys off. `system` writes nothing at all, so the CSS falls through
 * to `prefers-color-scheme`.
 */

const STORAGE_KEY = 'hrts.theme'
export const THEMES = ['light', 'dark', 'system']

const ThemeContext = createContext(null)

function readStored() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return THEMES.includes(value) ? value : 'system'
  } catch {
    return 'system'
  }
}

function apply(theme) {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStored)
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false)

  // index.html applies the stored value before first paint; this keeps the
  // attribute in step once React owns it.
  useEffect(() => { apply(theme) }, [theme])

  // On "system", follow the machine if it changes while the page is open --
  // otherwise a laptop switching to night mode leaves this page behind.
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!query) return undefined
    const onChange = (e) => setSystemDark(e.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const setTheme = useCallback((next) => {
    if (!THEMES.includes(next)) return
    setThemeState(next)
    apply(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* storage may be unavailable; the choice simply will not persist */
    }
  }, [])

  const isDark = theme === 'dark' || (theme === 'system' && systemDark)

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isDark }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}

const ICONS = { light: '☀', dark: '☾', system: '◐' }

/** The segmented control, used in the top bar and on the sign-in page. */
export function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  const { t } = useI18n()

  return (
    <div className="theme-switch" role="group" aria-label={t('theme.label')}>
      {THEMES.map((option) => (
        <button key={option} type="button"
                className={`theme-btn ${theme === option ? 'active' : ''}`}
                aria-pressed={theme === option}
                aria-label={t(`theme.${option}`)}
                title={t(`theme.${option}`)}
                onClick={() => setTheme(option)}>
          <span aria-hidden="true">{ICONS[option]}</span>
        </button>
      ))}
    </div>
  )
}
