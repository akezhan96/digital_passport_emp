import React, { useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import { worklistText } from '../i18n/worklists'

export function useDebounced(value, delay = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export default function WorklistPager({ total, offset, limit, onChange, disabled = false }) {
  const { lang } = useI18n()
  const l = worklistText[lang] || worklistText.ru
  return <div className="worklist-pagination">
    <span>{l.found}: {total} · {l.page} {Math.floor(offset / limit) + 1} {l.of} {Math.max(1, Math.ceil(total / limit))}</span>
    <div className="btn-row">
      <button className="btn btn-ghost btn-sm" disabled={disabled || offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}>{l.previous}</button>
      <button className="btn btn-ghost btn-sm" disabled={disabled || offset + limit >= total}
        onClick={() => onChange(offset + limit)}>{l.next}</button>
    </div>
  </div>
}
