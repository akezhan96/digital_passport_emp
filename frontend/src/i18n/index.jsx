import React, { useContext, useState, useCallback, useEffect } from 'react'
import { I18nContext } from './context'
import { ru } from './ru'
import { kk } from './kk'
import { additions, codes } from './workspace'
import { localizeText } from './text'

const DICTS = { ru: { ...ru, ...additions.ru }, kk: { ...kk, ...additions.kk } }
export const LANGUAGES = [
  { code: 'ru', label: 'Русский', short: 'RU' },
  { code: 'kk', label: 'Қазақша', short: 'KK' },
]

const STORAGE_KEY = 'hrts.lang'

function readStored() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return DICTS[value] ? value : 'ru'
  } catch {
    return 'ru'
  }
}

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(readStored)
  useEffect(() => {
    document.documentElement.lang = lang
    document.title = DICTS[lang].app.title
  }, [lang])

  const setLang = useCallback((next) => {
    if (!DICTS[next]) return
    setLangState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* storage may be unavailable; the choice simply won't persist */
    }
  }, [])

  /** Translate a dotted key, with {placeholder} substitution. */
  const t = useCallback(
    (key, vars) => {
      const lookup = (dict) =>
        key.split('.').reduce((acc, part) => (acc ? acc[part] : undefined), dict)
      let value = lookup(DICTS[lang])
      if (value === undefined) value = lookup(DICTS.ru)
      if (value === undefined) return key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          value = String(value).replaceAll(`{${k}}`, v)
        })
      }
      return value
    },
    [lang],
  )

  /** Pick the right localised column off a reference row. */
  const pick = useCallback(
    (row, base = 'name') => {
      if (!row) return ''
      return (
        row[`${base}_${lang}`] ||
        row[`${base}_ru`] ||
        row[base] ||
        ''
      )
    },
    [lang],
  )

  return (
    <I18nContext.Provider value={{ lang, setLang, t, pick,
      text: value => localizeText(value, lang),
      labelCode: (code) => String(code || '').split(':').map(part => codes[lang][part] || codes.ru[part] || part).join(': ') }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside I18nProvider')
  return ctx
}
