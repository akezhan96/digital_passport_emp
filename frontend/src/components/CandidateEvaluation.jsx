import React, { useEffect, useMemo, useState } from 'react'
import { candidateApi } from '../candidateApi'
import { errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { candidateText } from '../i18n/candidateMethodology'
import { candidatePointsPreview } from '../candidatePoints'
import { evaluationPayload, hasApplicableSources, hasDossierSource, methodologySections, criterionSection, orderedCriteria } from '../candidateSources'
import { DossierFieldValues } from './DossierFields'
import { evaluationDisplayState } from '../workflowUi'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { CANDIDATE_SCOPE, confirmUnsavedLeave } from '../unsavedChanges'
import '../candidate-methodology.css'

export const formatPoints = (value, lang) => value == null ? '—' : Number(value).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU', { maximumFractionDigits: 2 })

export function CandidateSummary({ summary, dirty = false, state = 'saved', onRecalculate, calculating = false, recalculateDisabled = false, sourceHint }) {
  const { lang } = useI18n()
  const copy = candidateText(lang)
  if (!summary) return null
  return <>
    <div className={`candidate-result${state === 'stale' ? ' candidate-result--stale' : ''}`}>
      <div><p>{copy.total}</p><strong>{formatPoints(summary.earned_points, lang)} / {formatPoints(summary.max_points, lang)}</strong><p>{copy.points}</p></div>
      <div className="candidate-result-value"><strong>{formatPoints(summary.percent, lang)}{summary.percent == null ? '' : '%'}</strong>
        {state === 'stale' && <span className="badge badge-warn" role="status">{copy.staleScore}</span>}
        {state === 'preview' && <span className="badge badge-info" role="status">{copy.previewScore}</span>}
        {state === 'saved' && summary.percent != null && <small className="muted">{copy.savedScoreLabel}</small>}
      </div>
      <div className="candidate-completeness"><strong>{summary.filled_count} / {summary.applicable_count}</strong><p>{copy.completeness}</p><small>{copy.completenessHint}</small></div>
      {onRecalculate && <div className="candidate-recalculate"><button type="button" className={state === 'stale' ? 'btn' : 'btn btn-ghost'} disabled={recalculateDisabled} onClick={onRecalculate}>{calculating ? copy.calculating : summary.percent == null ? copy.calculateFromDossier : copy.recalculate}</button>
        <small className="muted" role="status">{sourceHint}</small></div>}
    </div>
    {summary.partial_visibility && <p className="alert alert-info">{copy.partial}</p>}
    {!summary.complete && <p className="candidate-info">{copy.incomplete}</p>}
    {summary.invalid_count > 0 && <p className="alert alert-bad" role="alert">{copy.invalidScores}</p>}
    {dirty && <p className="candidate-info" role="status">{copy.unsaved}</p>}
  </>
}

export default function CandidateEvaluation({ employeeId, readOnly = false, onChanged, initialEvaluationId = null, initialMethodologyId = null }) {
  const { lang, pick } = useI18n()
  const { isAdmin } = useAuth()
  const copy = candidateText(lang)
  const [data, setData] = useState(null)
  const [values, setValues] = useState({})
  const [technical, setTechnical] = useState(false)
  const [note, setNote] = useState('')
  const [block, setBlock] = useState('general')
  const [methods, setMethods] = useState([])
  const [methodologyId, setMethodologyId] = useState(initialMethodologyId)
  const [historicalId, setHistoricalId] = useState(initialEvaluationId)
  const [history, setHistory] = useState(null)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState('')
  const [dirty, setDirty] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [sourcePreview, setSourcePreview] = useState(null)
  const [dossierStale, setDossierStale] = useState(false)
  const [fieldsMounted, setFieldsMounted] = useState(false)
  const [fieldsDirty, setFieldsDirty] = useState(false)
  const locked = readOnly || !isAdmin || Boolean(historicalId) || data?.read_only
  const markSaved = useUnsavedChanges(dirty, copy.discard, CANDIDATE_SCOPE)

  function accept(next) {
    setData(next)
    setValues(Object.fromEntries(next.scores.map(s => [s.position, String(s.points)])))
    setTechnical(next.technical_profile)
    setNote(next.note || '')
    setSourcePreview(null); setDossierStale(Boolean(next.source_stale))
    setBlock(previous => methodologySections(next.methodology).some(s => s.key === previous) ? previous : methodologySections(next.methodology)[0]?.key ?? '')
    markSaved()
    setDirty(false)
  }
  useEffect(() => { setHistoricalId(initialEvaluationId); setMethodologyId(initialMethodologyId); setHistoryOpen(false); setHistoryOffset(0); setMessage(''); setFieldsMounted(false); setFieldsDirty(false) }, [employeeId, initialEvaluationId, initialMethodologyId])
  useEffect(() => {
    let active = true
    candidateApi.models().then(({ data: rows }) => { if (active) setMethods(rows.filter(m => m.status !== 'draft')) })
      .catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null); setData(null); setDirty(false)
    candidateApi.evaluation(employeeId, historicalId || undefined, controller.signal, historicalId ? undefined : methodologyId || undefined)
      .then(({ data: next }) => { if (!controller.signal.aborted) accept(next) })
      .catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [employeeId, historicalId, methodologyId, refresh])
  useEffect(() => {
    if (!historyOpen) return
    let active = true
    candidateApi.history(employeeId, historyOffset).then(({ data: result }) => { if (active) setHistory(result) })
      .catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false }
  }, [employeeId, historyOpen, historyOffset, refresh])

  const sections = methodologySections(data?.methodology)
  const selectedSection = sections.find(section => section.key === block) || sections[0]
  const sectionCriteria = orderedCriteria(data?.methodology, selectedSection?.key).filter(c => c.enabled)
  const usesSources = Boolean(data && hasApplicableSources(data.methodology.criteria, technical))
  const summary = useMemo(() => {
    if (!data || !dirty) return data?.summary
    return candidatePointsPreview(data.methodology.criteria, values, technical, data.summary)
  }, [data, dirty, values, technical])
  const changeValue = (position, value) => { setValues(old => ({ ...old, [position]: value })); setDirty(true); setSourcePreview(null); setMessage('') }
  const showHistory = id => {
    if (!confirmUnsavedLeave(CANDIDATE_SCOPE)) return
    setDirty(false)
    setSourcePreview(null); setFieldsMounted(false); setFieldsDirty(false)
    setHistoricalId(id); setMessage('')
    if (id === historicalId) setRefresh(x => x + 1)
  }
  const chooseMethod = id => {
    if (!confirmUnsavedLeave(CANDIDATE_SCOPE)) return
    markSaved(); setDirty(false); setSourcePreview(null); setFieldsMounted(false); setFieldsDirty(false)
    setHistoricalId(null); setMethodologyId(Number(id)); setMessage('')
  }
  const save = async event => {
    event.preventDefault()
    if (locked || busy || !data) return
    setBusy(true); setError(null); setMessage('')
    try {
      if (fieldsDirty || (usesSources && !sourcePreview)) return
      const body = evaluationPayload(data, values, technical, note)
      if (usesSources) { body.source_fingerprint = sourcePreview.source_fingerprint; body.confirm_sources = true }
      const { data: next } = await candidateApi.saveEvaluation(employeeId, body)
      accept(next); setMessage(copy.saved); setRefresh(x => x + 1)
      onChanged?.()
    } catch (e) { setError(errorMessage(e)); if (usesSources) { setSourcePreview(null); setDossierStale(true) } }
    finally { setBusy(false) }
  }
  const previewSources = async () => {
    if (locked || busy || fieldsDirty || !data) return
    setBusy(true); setError(null); setMessage(''); setSourcePreview(null)
    try {
      const { data: preview } = await candidateApi.preview(employeeId, evaluationPayload(data, values, technical, note))
      setSourcePreview(preview)
      setValues(Object.fromEntries(preview.scores.map(score => [score.position, String(score.points)])))
      setDirty(true); setDossierStale(false)
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const displayState = evaluationDisplayState({ historical: Boolean(historicalId), stale: dossierStale && usesSources, preview: Boolean(sourcePreview), dirty, hasSavedScore: data?.summary?.percent != null })
  if (loading && !data) return <div className="spinner" />
  if (!data) return <p className="alert alert-bad" role="alert">{error || copy.noMethod}</p>
  return <div className="candidate-method">
    <div className="candidate-toolbar">
      {!historicalId && methods.length ? <label>{copy.methodName}<select value={methodologyId || data.methodology.id} disabled={busy || loading} onChange={e => chooseMethod(e.target.value)}>
        {methods.map(method => <option key={method.id} value={method.id}>{pick(method)} · {copy.version} {method.version}</option>)}
      </select></label> : <strong>{copy.version} {data.methodology.version} · {pick(data.methodology)}</strong>}
      <span className={`badge ${data.methodology.status === 'active' ? 'badge-ok' : data.methodology.status === 'draft' ? 'badge-warn' : 'badge-closed'}`}>{copy[data.methodology.status]}</span>
      {historicalId && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => showHistory(null)}>{copy.recordNew}</button>}
    </div>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    {message && <p className="alert alert-ok" role="status">{message}</p>}
    {historicalId && <p className="alert alert-info">{copy.historical}</p>}
    {!historicalId && dossierStale && usesSources && <p className="alert alert-info" role="status">{copy.sourceStale}</p>}
    <CandidateSummary summary={summary} dirty={dirty} state={displayState}
      onRecalculate={!locked && usesSources ? previewSources : undefined} calculating={busy}
      recalculateDisabled={busy || loading || fieldsDirty}
      sourceHint={fieldsDirty ? copy.saveFieldsFirst : sourcePreview ? copy.previewReady : copy.sourcesNeedPreview} />
    {!historicalId && <details className="candidate-dossier-details" onToggle={e => { if (e.currentTarget.open) setFieldsMounted(true) }}>
      <summary>{copy.dossierFields}{fieldsDirty && <span className="muted"> · {copy.unsaved}</span>}</summary>
      {fieldsMounted && <DossierFieldValues employeeId={employeeId} readOnly={locked || busy} onDirtyChange={setFieldsDirty} onSaved={() => { setSourcePreview(null); setDossierStale(true); setMessage(copy.fieldsSaved) }} />}
    </details>}
    <form onSubmit={save}>
      <fieldset disabled={locked || busy || loading} style={{ border: 0, margin: 0, padding: 0 }}>
        {sections.some(section => section.kind === 'technical') && <label className="candidate-technical"><input type="checkbox" checked={technical} onChange={e => { setTechnical(e.target.checked); setDirty(true); setSourcePreview(null) }} />{copy.technicalProfile}</label>}
      </fieldset>
      <div className="candidate-tabs" role="group" aria-label={copy.criteria}>
        {sections.map(section => <button type="button" key={section.key} className={selectedSection?.key === section.key ? 'active' : ''} aria-pressed={selectedSection?.key === section.key} onClick={() => setBlock(section.key)}>{pick(section)}<small>{data.methodology.criteria.filter(c => criterionSection(c) === section.key && c.enabled).length}</small></button>)}
      </div>
      {selectedSection?.kind === 'technical' && !technical ? <p className="alert alert-info">{copy.notApplicable}</p> : <div className="candidate-scroll">
        <table className="candidate-score-table"><thead><tr><th>№</th><th>{copy.name}</th><th>{copy.received}</th></tr></thead>
          <tbody>{sectionCriteria.map((c, index) => <tr key={c.id}>
            <td>{index + 1}</td><td><label htmlFor={`candidate-score-${employeeId}-${c.position}`}>{pick(c)}</label>{hasDossierSource(c) && <small className="candidate-source-note">{copy.fromDossier}</small>}</td>
            <td>{locked || hasDossierSource(c) ? <strong>{values[c.position] == null || values[c.position] === '' ? '—' : formatPoints(values[c.position], lang)}</strong> : <input id={`candidate-score-${employeeId}-${c.position}`} type="number" min="0" max={c.max_points} step="0.01" value={values[c.position] ?? ''}
              placeholder="—" aria-label={`${pick(c)} · ${copy.maximum}: ${c.max_points}`} disabled={busy || loading} onChange={e => changeValue(c.position, e.target.value)} />} <span className="muted">/ {formatPoints(c.max_points, lang)}</span></td>
          </tr>)}{!sectionCriteria.length && <tr><td colSpan={3} className="empty">{copy.noCriteria}</td></tr>}</tbody></table>
      </div>}
      {!!(sourcePreview?.source_evidence || data.source_evidence)?.length && <SourceEvidence rows={sourcePreview?.source_evidence || data.source_evidence} methodology={data.methodology} preview={Boolean(sourcePreview)} />}
      {isAdmin && <div className="field"><label htmlFor={`candidate-note-${employeeId}`}>{copy.note}</label>
        <textarea id={`candidate-note-${employeeId}`} rows={2} maxLength={2000} value={note} disabled={locked || busy || loading} onChange={e => { setNote(e.target.value); setDirty(true); setSourcePreview(null) }} />
        <small className="muted">{copy.noteHint}</small></div>}
      <div className="candidate-toolbar">
        {!locked && <button className="btn" type="submit" disabled={busy || loading || fieldsDirty || !dirty || (usesSources && !sourcePreview)}>{busy ? copy.saving : usesSources ? copy.confirmAndSave : copy.save}</button>}
        <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => setHistoryOpen(value => !value)} aria-expanded={historyOpen}>{copy.history}</button>
        {data.evaluated_by && <span className="muted">{copy.author}: {data.evaluated_by}</span>}
      </div>
    </form>
    {historyOpen && <div className="candidate-history">
      {!history ? <div className="spinner" /> : !history.items.length ? <p className="muted">{copy.historyEmpty}</p> : history.items.map(item => <button key={item.id} type="button" className="candidate-history-item" onClick={() => showHistory(item.id)}>
        <span>{copy.version} {item.summary.version} · {copy.revision} {item.revision}<small>{new Date(item.created_at + (item.created_at.endsWith('Z') ? '' : 'Z')).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU')} · {item.evaluated_by}</small></span>
        <span>{formatPoints(item.summary.earned_points, lang)} / {formatPoints(item.summary.max_points, lang)}<small>{formatPoints(item.summary.percent, lang)}{item.summary.percent == null ? '' : '%'}</small></span>
      </button>)}
      {history && history.total > 20 && <div className="candidate-pagination"><button className="btn btn-ghost btn-sm" disabled={!historyOffset} onClick={() => setHistoryOffset(x => Math.max(0, x - 20))}>{copy.previous}</button>
        <span>{historyOffset + 1}–{Math.min(historyOffset + 20, history.total)} / {history.total}</span><button className="btn btn-ghost btn-sm" disabled={historyOffset + 20 >= history.total} onClick={() => setHistoryOffset(x => x + 20)}>{copy.next}</button></div>}
    </div>}
  </div>
}

function SourceEvidence({ rows, methodology, preview }) {
  const { lang, pick } = useI18n()
  const copy = candidateText(lang)
  const value = row => row[`value_label_${lang}`] ?? row.value_label_ru ?? (row.value === true ? copy.yes : row.value === false ? copy.no : row.value ?? '—')
  return <details className="candidate-source-evidence" open={preview}>
    <summary>{preview ? copy.previewTitle : copy.savedSources}</summary>
    <div className="candidate-scroll"><table><thead><tr><th>{copy.name}</th><th>{copy.source}</th><th>{copy.value}</th><th>{copy.points}</th></tr></thead><tbody>
      {rows.filter(Boolean).map(row => <tr key={row.position}><td>{pick(methodology.criteria.find(c => c.position === row.position)) || row.position}</td>
        <td>{row[`source_label_${lang}`] || row.source_label_ru || copy.fromDossier}</td><td>{row.status === 'missing' ? copy.notFilled : String(value(row))}
          {row.source?.kind === 'tab_field' && row.evidence?.record_count > 1 && <small>{copy.tabValueCount}: {row.evidence.record_count}</small>}</td>
        <td><strong>{formatPoints(row.points, lang)}</strong>{row.status === 'no_match' && <small>{copy.noRuleMatch}</small>}</td></tr>)}
    </tbody></table></div>
  </details>
}
