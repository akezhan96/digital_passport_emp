import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { worklistText } from '../i18n/worklists'
import { vacancyText } from '../i18n/vacancyMethodology'
import { recruitmentText } from '../i18n/recruitment'
import { resultScore, recruitmentLink, recruitmentQuery, decisionClass, decisionTone } from '../recruitment'
import CalculationCard from '../components/MatchingResultCard'
import { confirmUnsavedLeave } from '../unsavedChanges'
import WorklistPager, { useDebounced } from '../components/WorklistPager'
import './worklists.css'

export default function MatchingPage() {
  const { t, pick, lang, labelCode } = useI18n()
  const l = worklistText[lang] || worklistText.ru
  const v = vacancyText(lang)
  const c = recruitmentText(lang)
  const [entry] = useState(recruitmentQuery)
  const [vacancies, setVacancies] = useState([])
  const [vacancyId, setVacancyId] = useState(() => String(entry.vacancy || ''))
  const [vacancySearch, setVacancySearch] = useState('')
  const [activeRun, setActiveRun] = useState(null)
  const [history, setHistory] = useState(null)
  const [historySearch, setHistorySearch] = useState('')
  const [historyOffset, setHistoryOffset] = useState(0)
  const [historyStatus, setHistoryStatus] = useState('')
  const [historyOpen, setHistoryOpen] = useState(true)
  const [createOpen, setCreateOpen] = useState(Boolean(entry.vacancy && !entry.run))
  const [results, setResults] = useState(null)
  const [resultOffset, setResultOffset] = useState(0)
  const [resultSearch, setResultSearch] = useState('')
  const [qualified, setQualified] = useState('')
  const [decision, setDecision] = useState('')
  const [reveal, setReveal] = useState(entry.names)
  const [selectedId, setSelectedId] = useState(entry.result)
  const [detail, setDetail] = useState(null)
  const [detailBusy, setDetailBusy] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const historyQuery = useDebounced(historySearch)
  const resultQuery = useDebounced(resultSearch)

  useEffect(() => {
    let active = true
    api.vacancies().then(r => { if (active) setVacancies(r.data.data) })
      .catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false }
  }, [refresh])
  useEffect(() => {
    if (!entry.run) return
    let live = true
    api.matchingRun(entry.run).then(r => { if (live) { setActiveRun(r.data); setHistoryOpen(false) } })
      .catch(e => { if (live) setError(errorMessage(e)) })
    return () => { live = false }
  }, [entry])
  useEffect(() => {
    let active = true
    setHistory(null)
    api.matchingRuns({ q: historyQuery, status: historyStatus || undefined, offset: historyOffset, limit: 8 })
      .then(r => { if (active) setHistory(r.data) })
      .catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false }
  }, [historyQuery, historyOffset, historyStatus, refresh])
  useEffect(() => {
    if (!activeRun) return
    let active = true
    setLoading(true)
    api.matchingResults(activeRun.id, reveal, { paged: true, limit: 20, offset: resultOffset,
      q: resultQuery, qualified: qualified || undefined, decision: decision || undefined })
      .then(r => { if (active) setResults(r.data) })
      .catch(e => { if (active) setError(errorMessage(e)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [activeRun, reveal, resultOffset, resultQuery, qualified, decision, refresh])
  useEffect(() => {
    setDetail(null); setDetailError(null); setDetailBusy(false)
    if (!selectedId || !activeRun) return
    let active = true
    setDetailBusy(true)
    api.matchingResult(selectedId, reveal)
      .then(r => { if (active) { if (r.data.run_id !== activeRun.id) setDetailError(c.resultUnavailable); else setDetail(r.data) } })
      .catch(e => { if (active) setDetailError(errorMessage(e)) })
      .finally(() => { if (active) setDetailBusy(false) })
    return () => { active = false }
  }, [selectedId, activeRun?.id, reveal, refresh])

  const chooseRun = (row) => {
    if (!confirmUnsavedLeave()) return
    setActiveRun(row); setReveal(false); setSelectedId(null); setDetail(null); setResults(null)
    setResultOffset(0); setResultSearch(''); setQualified(''); setDecision(''); setHistoryOpen(false)
    setCreateOpen(false); setError(null); setNotice('')
  }
  const run = async event => {
    event.preventDefault()
    if (!vacancyId) return
    setBusy(true); setError(null)
    try {
      const { data } = await api.runMatching({ vacancy_id: Number(vacancyId) })
      if (data.status !== 'completed') { setError(data.error_message || l.failed); setRefresh(value => value + 1); return }
      chooseRun({ ...data, vacancy_title: vacancies.find(v => v.id === Number(vacancyId))?.title, vacancy_title_kk: vacancies.find(v => v.id === Number(vacancyId))?.title_kk })
      setHistoryOffset(0); setRefresh(value => value + 1)
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const chosen = vacancies.find(v => v.id === Number(vacancyId))
  const shownVacancies = vacancies.filter(v => v.id === Number(vacancyId)
    || [v.title,v.title_kk].some(value => (value || '').toLocaleLowerCase().includes(vacancySearch.toLocaleLowerCase())))
  const chooseResult = id => { if (!confirmUnsavedLeave()) return; setSelectedId(id); setNotice(''); setError(null) }
  const resetFilter = setter => event => { if (!confirmUnsavedLeave()) return; setter(event.target.value); setResultOffset(0); setSelectedId(null); setNotice('') }
  const vacancyTitle = row => { const vacancy = vacancies.find(item => item.id === row.vacancy_id) || {}; return lang === 'kk' ? row.vacancy_title_kk || row.title_kk || vacancy.title_kk || row.vacancy_title || row.title || vacancy.title : row.vacancy_title || row.title || vacancy.title }
  const readiness = code => code === 'review_ready' ? v.complete : code === 'needs_review' ? v.review : code === 'not_assessed' ? v.noScore : labelCode(code)
  const statusLabel = status => status === 'completed' ? l.processed : status === 'processing' ? l.processing : l.failed

  return <>
    <div className="worklist-toolbar" style={{ marginBottom: 14, justifyContent: 'space-between' }}>
      <h2 style={{ margin: 0 }}>{t('matching.title')}</h2>
      <button className="btn" onClick={() => setCreateOpen(value => !value)}>{l.newRun}</button>
    </div>
    {error && <div className="alert alert-bad">{error}</div>}
    {notice && <div className="alert alert-ok" role="status">{c[notice]}</div>}
    {createOpen && <section className="card">
      <form onSubmit={run}>
        <div className="worklist-toolbar">
          <div className="field"><label htmlFor="match-vacancy-search">{l.historySearch}</label>
            <input id="match-vacancy-search" type="search" value={vacancySearch} onChange={e => setVacancySearch(e.target.value)} /></div>
          <div className="field"><label htmlFor="match-vacancy">{t('matching.selectVacancy')}</label>
            <select id="match-vacancy" value={vacancyId} onChange={e => setVacancyId(e.target.value)}>
              <option value="">—</option>{shownVacancies.map(v => <option key={v.id} value={v.id}>{vacancyTitle(v)}</option>)}
            </select></div>
          <button className="btn" disabled={busy || !chosen || chosen.status === 'closed' || (!chosen.candidate_methodology_id && chosen.total_weight !== 100)}>
            {busy ? t('matching.running') : t('matching.run')}</button>
        </div>
        {chosen && !chosen.candidate_methodology_id && chosen.total_weight !== 100 && <div className="alert alert-warn" style={{ marginTop: 12 }}>{t('vacancy.weightError')} ({chosen.total_weight})</div>}
        {chosen?.candidate_methodology_id && <p className="muted">{v.method} · v{chosen.methodology_version} · ≥ {chosen.min_candidate_percent}% · {chosen.requires_technical_profile ? v.technical : v.anyProfile}</p>}
      </form>
    </section>}
    <details className="card flush worklist-section" open={historyOpen} onToggle={e => setHistoryOpen(e.currentTarget.open)}>
      <summary>{l.history}{history ? ` · ${history.total}` : ''}</summary>
      <div className="worklist-toolbar">
        <input aria-label={l.historySearch} type="search" placeholder={l.historySearch} value={historySearch}
          onChange={e => { setHistorySearch(e.target.value); setHistoryOffset(0) }} />
        <select aria-label={t('common.status')} value={historyStatus} onChange={e => { setHistoryStatus(e.target.value); setHistoryOffset(0) }}>
          <option value="">{l.all}</option>{['completed', 'processing', 'error'].map(code => <option key={code} value={code}>{statusLabel(code)}</option>)}
        </select>
      </div>
      {!history ? <div className="spinner" /> : <>
        <div className="worklist-table-scroll"><table><thead><tr><th>{t('vacancy.title')}</th><th>{t('common.status')}</th><th className="num">{l.results}</th></tr></thead>
          <tbody>{history.data.length === 0 ? <tr><td colSpan={3}><div className="empty">{l.noResults}</div></td></tr> : history.data.map(row =>
            <tr key={row.id} className={activeRun?.id === row.id ? 'active' : ''}><td>
              <button className="worklist-select" onClick={() => chooseRun(row)}><strong>{vacancyTitle(row)}</strong>
                <small className="muted">№ {row.id} · {new Date(`${row.created_at}${/[Z+-]\d\d:?\d\d$/.test(row.created_at) || row.created_at.endsWith('Z') ? '' : 'Z'}`).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU')}</small></button>
            </td><td><span className={`badge ${row.status === 'completed' ? 'badge-ok' : row.status === 'processing' ? 'badge-info' : 'badge-bad'}`}>{statusLabel(row.status)}</span></td><td className="num">{row.total_qualified} / {row.total_evaluated}</td></tr>)}</tbody></table></div>
        <WorklistPager total={history.total} offset={historyOffset} limit={8} onChange={setHistoryOffset} />
      </>}
    </details>
    {!activeRun ? <div className="card"><div className="empty">{l.historyHint}</div></div> : <>
      <div className="matching-summary"><strong>{vacancyTitle(activeRun)}</strong><span>№ {activeRun.id}</span>
        {results && <><span>{t('matching.evaluated')}: {results.total_evaluated}</span><span>{t('matching.qualified')}: {results.total_qualified}</span></>}
        <a href={recruitmentLink('vacancies', { vacancy: activeRun.vacancy_id })}>{c.viewVacancy}</a>
      </div>
      {results?.candidate_methodology_id && <p className="muted recruitment-context">{v.method} · v{results.methodology_snapshot?.methodology?.version} · ≥ {results.methodology_snapshot?.min_candidate_percent}%{!results.include_confidential && <> · {v.public}</>}</p>}
      <div className="matching-workspace">
        <section className="card flush" aria-busy={loading}>
          <div className="structure-members-toolbar"><div className="worklist-toolbar">
            <input type="search" aria-label={reveal ? l.nameSearch : l.candidateSearch} placeholder={reveal ? l.nameSearch : l.candidateSearch}
              value={resultSearch} onChange={resetFilter(setResultSearch)} />
            <button className="btn btn-ghost btn-sm" onClick={() => { if (!confirmUnsavedLeave()) return; setReveal(value => !value); setResultSearch(''); setResultOffset(0); setDetail(null); setResults(null) }}>
              {reveal ? t('matching.hideNames') : t('matching.revealNames')}</button>
          </div><div className="worklist-toolbar" style={{ marginTop: 8 }}>
            <select aria-label={l.results} value={qualified} onChange={resetFilter(setQualified)}>
              <option value="">{l.allResults}</option><option value="true">{t('matching.shortlist')}</option><option value="false">{t('matching.potential')}</option>
            </select><select aria-label={t('matching.decision')} value={decision} onChange={resetFilter(setDecision)}>
              <option value="">{l.all}</option><option value="none">{l.noDecision}</option>
              {['selected', 'rejected', 'on_hold', 'reserve'].map(code => <option key={code} value={code}>{labelCode(code)}</option>)}
            </select></div>
          </div>
          {loading ? <div className="spinner" /> : results && <>
            <div className="worklist-table-scroll"><table><thead><tr><th>{l.candidate}</th><th className="num">{c.score}</th></tr></thead><tbody>
              {results.data.length === 0 ? <tr><td colSpan={2}><div className="empty">{l.noResults}</div></td></tr> : results.data.map(row =>
                <tr key={row.id} className={`matching-result-row ${selectedId === row.id ? 'active' : ''} ${row.decision ? `status-row ${decisionTone(row.decision.decision)}` : !row.is_qualified ? 'status-row status-warning' : ''}`} onClick={() => chooseResult(row.id)} aria-selected={selectedId === row.id}><td><button className="worklist-select" onClick={event => { event.stopPropagation(); chooseResult(row.id) }}>
                  <strong>{row.system_rank}. {row.display_name}</strong><small className="muted">{readiness(row.readiness_code)}</small>
                  {row.decision && <span className={`badge ${decisionClass(row.decision.decision)}`}>{c[row.decision.decision] || labelCode(row.decision.decision)}</span>}
                </button></td><td className="num"><strong>{resultScore(row, lang).percent}</strong>{resultScore(row, lang).points && <small className="matching-points">{resultScore(row, lang).points} {l.points}</small>}</td></tr>)}
            </tbody></table></div>
            <WorklistPager total={results.total} offset={resultOffset} limit={20} disabled={loading} onChange={value => { if (!confirmUnsavedLeave()) return; setResultOffset(value); setSelectedId(null) }} />
          </>}
        </section>
        <section>{detailBusy && selectedId ? <div className="spinner" /> : detailError ? <div className="card"><div className="alert alert-bad" role="alert">{detailError}</div><button className="btn" onClick={() => setRefresh(value => value + 1)}>{c.retry}</button></div> : detail ? <CalculationCard key={detail.id} row={detail} t={t} pick={pick} namesRevealed={reveal}
          onReveal={() => { if (confirmUnsavedLeave()) setReveal(true) }}
          onAppointed={() => { setNotice('appointedSaved'); setRefresh(value => value + 1) }}
          onDecision={async body => { await api.recordDecision(detail.id, body); setNotice('decisionSaved'); setRefresh(value => value + 1) }} />
          : <div className="card"><div className="empty">{l.selectResult}</div></div>}</section>
      </div>
    </>}
  </>
}

