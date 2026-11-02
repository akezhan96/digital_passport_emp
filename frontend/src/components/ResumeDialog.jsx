import React, { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n, LANGUAGES } from '../i18n'

const SECTIONS = ['career', 'education', 'languages', 'training', 'metrics']
export default function ResumeDialog({ employee, onClose }) {
  const { t, lang } = useI18n()
  const dialog = useRef(null)
  const [docLang, setDocLang] = useState(lang)
  const [sections, setSections] = useState(SECTIONS)
  const [contacts, setContacts] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => { dialog.current.showModal() }, [])
  const toggle = key => setSections(old => old.includes(key) ? old.filter(x => x !== key) : [...old, key])
  const generate = async format => {
    setBusy(true); setError(null)
    try {
      const { data } = await api.documentDownload(employee.id, { template: 'resume', format, lang: docLang, sections: sections.join(','), contacts })
      const url = URL.createObjectURL(data), link = document.createElement('a')
      link.href = url; link.download = `Resume_${employee.id}.${format}`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (e.response?.data instanceof Blob) {
        try { e.response.data = JSON.parse(await e.response.data.text()) } catch { /* use the standard connection message */ }
      }
      setError(errorMessage(e))
    } finally { setBusy(false) }
  }
  return <dialog className="resume-dialog" ref={dialog} onCancel={onClose} aria-labelledby="resume-title"
    onClick={e => { if (e.target === dialog.current && !busy) onClose() }}>
    <div className="section-heading"><h2 id="resume-title">{t('resume.title')}</h2><button className="btn btn-ghost btn-sm" onClick={onClose} aria-label={t('common.close')}>×</button></div>
    <p className="resume-person">{employee.last_name} {employee.first_name} {employee.middle_name || ''}</p>
    <p className="page-hint">{t('resume.hint')}</p>
    <div className="field"><label htmlFor="resume-lang">{t('documents.language')}</label>
      <select id="resume-lang" value={docLang} onChange={e => setDocLang(e.target.value)}>{LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}</select></div>
    <fieldset className="resume-sections"><legend>{t('resume.sections')}</legend>
      {SECTIONS.map(key => <label key={key}><input type="checkbox" checked={sections.includes(key)} onChange={() => toggle(key)} />{t(`employee.tabs.${key}`)}</label>)}
    </fieldset>
    <label className="resume-contact"><input type="checkbox" checked={contacts} onChange={e => setContacts(e.target.checked)} />{t('resume.contacts')}</label>
    <p className="muted">{t('resume.privacy')}</p>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    <div className="btn-row"><button className="btn" disabled={busy || !sections.length} onClick={() => generate('docx')}>{busy ? t('resume.generating') : t('resume.word')}</button>
      <button className="btn btn-ghost" disabled={busy || !sections.length} onClick={() => generate('pdf')}>{t('resume.pdf')}</button></div>
  </dialog>
}
