import React, { useState } from 'react'
import { api } from '../api'
import { useI18n, LANGUAGES } from '../i18n'

/** Download the employee record sheet as PDF or DOCX. */
export default function EmployeeDocuments({ employeeId }) {
  const { t, lang } = useI18n()
  const [docLang, setDocLang] = useState(lang)

  // The browser sends the HttpOnly session cookie; no token appears in the URL.
  const open = (format) => {
    window.open(api.documentUrl(employeeId, format, docLang), '_blank',
                'noopener,noreferrer')
  }

  return (
    <div className="card">
      <h3>{t('documents.title')}</h3>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        {t('documents.hint')}
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end',
                    flexWrap: 'wrap' }}>
        <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
          <label>{t('documents.language')}</label>
          <select value={docLang} onChange={(e) => setDocLang(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
        </div>
        <button className="btn" onClick={() => open('pdf')}>
          {t('documents.download')} · {t('documents.pdf')}
        </button>
        <button className="btn btn-ghost" onClick={() => open('docx')}>
          {t('documents.download')} · {t('documents.docx')}
        </button>
      </div>
    </div>
  )
}
