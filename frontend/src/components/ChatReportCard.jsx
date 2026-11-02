import React, { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

export default function ChatReportCard({ request }) {
  const { t } = useI18n()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [building, setBuilding] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState(null)
  const [retry, setRetry] = useState(0)
  const [visible, setVisible] = useState(false)
  const element = useRef(null)
  const version = useRef(0)
  const alive = useRef(true)
  const buildingLock = useRef(false)
  const downloadLock = useRef(false)
  const plan = request.plan
  const spec = report?.spec || plan.spec
  const snapshot = report?.snapshot

  // A long history must not fetch every report snapshot merely to open a chat.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect() }
    }, { rootMargin: '200px' })
    if (element.current) observer.observe(element.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; version.current += 1 }
  }, [])
  useEffect(() => {
    if (!visible) return
    const token = ++version.current
    let valid = true
    const current = () => valid && alive.current && version.current === token
    setLoading(true); setError(null)
    const load = async () => {
      try {
        const { data: versions } = await api.assistantReports(request.conversation_id, request.id)
        if (!current()) return
        const id = versions.data[0]?.id || plan.report_id
        if (id) {
          const { data } = await api.assistantReport(id)
          if (current()) setReport(data)
        } else if (current()) setReport(null)
      } catch (e) { if (current()) setError(errorMessage(e)) }
      finally { if (current()) setLoading(false) }
    }
    load()
    return () => { valid = false }
  }, [request.id, plan.report_id, retry, visible])

  const build = async reveal => {
    if (buildingLock.current || downloadLock.current || !spec) return
    buildingLock.current = true
    const token = ++version.current
    const current = () => alive.current && version.current === token
    setBuilding(true); setError(null)
    // Name disclosure is an explicit action. Never silently drop another
    // requested column when the eight-column limit has already been reached.
    let columns = (spec.columns || []).filter(key => reveal || key !== 'name')
    if (reveal && !columns.includes('name')) {
      columns = [...columns, 'name']
    }
    try {
      const { data } = await api.assistantReportPreview(request.id, { ...spec, columns: columns.length ? columns : ['code'] }, reveal)
      if (current()) setReport(data)
    } catch (e) { if (current()) setError(errorMessage(e)) }
    finally { buildingLock.current = false; if (current()) setBuilding(false) }
  }
  const download = async () => {
    if (!report || downloadLock.current) return
    downloadLock.current = true
    const token = version.current
    const current = () => alive.current && version.current === token
    setDownloading(true); setError(null)
    try {
      const { data } = await api.assistantReportDocument(report.id)
      if (!current()) return
      const url = URL.createObjectURL(data), link = document.createElement('a')
      link.href = url
      link.download = `${(snapshot?.title || spec.title || t('assistantReport.shortLabel')).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 80)}.docx`
      document.body.appendChild(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (e.response?.data instanceof Blob) {
        try { e.response.data = JSON.parse(await e.response.data.text()) } catch { /* Use the local connection message. */ }
      }
      if (current()) setError(errorMessage(e))
    } finally { downloadLock.current = false; if (current()) setDownloading(false) }
  }
  const canAddNames = spec?.layout !== 'summary' && !snapshot?.reveal_names
    && (spec?.columns?.length < 8 || spec?.columns?.includes('name'))
  return <div ref={element} className="chat-report-card" aria-busy={loading || building}>
    <div className="chat-report-file"><span className="chat-report-icon" aria-hidden="true">W</span><div className="chat-report-details"><strong>{snapshot?.title || spec?.title || t('assistantReport.shortLabel')}</strong>
      <p className="chat-report-meta">Word · {spec?.lang === 'kk' ? 'Қазақша' : 'Русский'}{spec?.layout && <> · {t(`assistantReport.layouts.${spec.layout}`)}</>}{spec?.orientation && <> · {t(`assistantReport.${spec.orientation}`)}</>}</p>
    </div></div>
    {loading ? <p className="chat-report-meta" role="status">{t('common.loading')}</p> : <>
      {report && <><p className="chat-report-meta">{t('assistantChat.reportReady')} · {t(snapshot?.reveal_names ? 'assistantChat.namesIncluded' : 'assistantChat.namesHidden')}</p>
        <div className="chat-report-actions"><button className="btn btn-sm" disabled={downloading || building} onClick={download}>{downloading ? t('common.loading') : t('assistantReport.download')}</button></div>
        {!!snapshot?.sections?.length && <details className="chat-report-contents"><summary>{t('assistantChat.reportContents', { count: snapshot.sections.length })}</summary><ol>{snapshot.sections.map((section, i) => <li key={i}><strong>{section.question}</strong><span>{section.count} / {section.total} · {section.percent}%</span></li>)}</ol></details>}
        {canAddNames && <div className="chat-report-consent"><button className="chat-text-button" disabled={building || downloading} onClick={() => build(true)}>{t('assistantChat.addNames')}</button>{plan.requested_names && <p>{t('assistantChat.namesConsent')}</p>}</div>}
        {!canAddNames && !snapshot?.reveal_names && spec?.layout !== 'summary' && <p className="chat-report-meta">{t('assistantChat.namesColumnLimit')}</p>}
        {building && <p className="chat-report-meta" role="status">{t('assistantReport.building')}</p>}
      </>}
      {!report && !error && <button className="btn btn-ghost btn-sm" disabled={building} onClick={() => build(false)}>{building ? t('assistantReport.building') : t('assistantChat.buildLegacyReport')}</button>}
    </>}
    {error && <div className="chat-inline-error" role="alert">{error}{!report && <button className="chat-text-button" onClick={() => setRetry(value => value + 1)}>{t('errors.retry')}</button>}</div>}
  </div>
}
