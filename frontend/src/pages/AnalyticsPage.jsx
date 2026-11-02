import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import ConditionBuilder from '../components/ConditionBuilder'
import QueryBuilder from '../components/QueryBuilder'
import QueryResult from '../components/QueryResult'
import DisposalStatistics, { disposalText } from '../components/DisposalStatistics'
import EmployeeRanking from '../components/EmployeeRanking'
import { rankingText } from '../i18n/employeeRanking'

/**
 * Three ways to ask the same base a question:
 *   - ready-made questions, for what HR asks most often;
 *   - a builder, for everything else;
 *   - saved queries, for the ones worth keeping.
 */
export default function AnalyticsPage() {
  const { t, lang } = useI18n()
  const target = new URLSearchParams(location.hash.split('?')[1]).get('tab')
  const tab = ['ranking', 'disposal', 'build', 'saved'].includes(target) ? target : 'ready'
  const showOverview = tab !== 'ranking' && tab !== 'disposal'
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (showOverview) api.analyticsOverview().then((r) => setOverview(r.data)).catch(() => {})
  }, [showOverview])

  return (
    <>
      <h2>{t('analytics.title')}</h2>
      {showOverview && <p className="page-hint">{t('analytics.hint')}</p>}

      {error && <div className="alert alert-bad">{error}</div>}

      {showOverview && overview && (
        <div className="grid grid-4">
          {overview.cards.map((card) => (
            <div className="card stat" key={card.code}>
              <div className="stat-value">{card.value}</div>
              <div className="stat-label">
                {card[`label_${lang}`] || card.label_ru}
                <span className="muted"> · {card.percent}%</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <nav className="tabs analytics-views" aria-label={t('analytics.title')}>
        {[['ready', t('builder.readyTab')], ['ranking', rankingText(lang).title],
          ['disposal', disposalText[lang].title], ['build', t('builder.tab')], ['saved', t('builder.savedTab')]].map(([key, label]) =>
          <a key={key} className={`tab ${tab === key ? 'active' : ''}`} aria-current={tab === key ? 'page' : undefined}
            href={key === 'ready' ? '#/analytics' : `#/analytics?tab=${key}`}>{label}</a>)}
      </nav>

      {tab === 'ready' && <ReadyQuestions onError={setError} />}
      {tab === 'ranking' && <EmployeeRanking />}
      {tab === 'disposal' && <DisposalStatistics /> }
      {tab === 'build' && <CustomQuery onError={setError} />}
      {tab === 'saved' && <SavedQueries onError={setError} />}
    </>
  )
}

/* ------------------------------------------------------------------ ready */

function ReadyQuestions({ onError }) {
  const { t, lang } = useI18n()
  const [questions, setQuestions] = useState([])
  const [code, setCode] = useState('')
  const [params, setParams] = useState({})
  const [result, setResult] = useState(null)
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.analyticsQuestions()
      .then((r) => setQuestions(r.data.data))
      .catch((e) => onError(errorMessage(e)))
  }, [onError])

  const question = questions.find((q) => q.code === code)
  const label = (q) => q[`name_${lang}`] || q.name_ru

  const choose = (next) => {
    setCode(next)
    setResult(null)
    setReveal(false)
    const chosen = questions.find((q) => q.code === next)
    const seed = {}
    ;(chosen?.fields || []).forEach((f) => {
      if (f.multiple) seed[f.key] = []
      else if (f.default !== undefined) seed[f.key] = f.default
    })
    setParams(seed)
  }

  const run = useCallback(async (withNames) => {
    if (!code) return
    setBusy(true)
    onError(null)
    try {
      const r = await api.analyticsRun(code, params, withNames)
      setResult(r.data)
      setReveal(withNames)
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [code, params, onError])

  return (
    <div className="split">
      <div className="card flush">
        <div style={{ padding: '12px 14px',
                      borderBottom: '1px solid var(--slate-200)' }}>
          <strong style={{ fontSize: 13 }}>{t('analytics.selectQuestion')}</strong>
        </div>
        <div className="list">
          {questions.map((q) => (
            <div key={q.code}
                 className={`list-row ${code === q.code ? 'active' : ''}`}
                 onClick={() => choose(q.code)}>
              <div>
                <div className="list-title">{label(q)}</div>
                {q.fields.length > 0 && (
                  <div className="list-sub">
                    {q.fields.length} {t('analytics.parameters').toLowerCase()}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        {!question ? (
          <div className="card"><div className="empty">
            {t('analytics.noResult')}
          </div></div>
        ) : (
          <>
            <div className="card">
              <h3>{label(question)}</h3>
              {question.fields.length > 0 ? (
                <div style={{ border: '1px solid var(--slate-200)',
                              borderRadius: 6, padding: '14px 16px',
                              marginBottom: 14 }}>
                  <ConditionBuilder
                    schema={{ fields: question.fields,
                              [`hint_${lang}`]: question[`hint_${lang}`],
                              hint_ru: question.hint_ru }}
                    value={params} onChange={setParams} />
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 12.5,
                                                marginBottom: 14 }}>
                  {question[`hint_${lang}`] || question.hint_ru}
                </div>
              )}
              <button className="btn" onClick={() => run(reveal)} disabled={busy}>
                {busy ? t('analytics.running') : t('analytics.run')}
              </button>
            </div>

            <QueryResult result={result} reveal={reveal}
                         onToggleReveal={() => run(!reveal)} />
          </>
        )}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- custom */

function CustomQuery({ onError }) {
  const { t, lang } = useI18n()
  const [draft, setDraft] = useState({
    definition: { match: 'all', conditions: [] }, group_by: null,
  })
  const [result, setResult] = useState(null)
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('')
  const [saved, setSaved] = useState(false)

  const conditions = draft.definition?.conditions || []
  const ready = conditions.length > 0
    && conditions.every((c) => c.field && c.operator)

  const run = async (withNames) => {
    if (!ready) return
    setBusy(true)
    onError(null)
    try {
      const r = await api.analyticsPreview(draft.definition, draft.group_by,
                                           withNames, lang)
      setResult(r.data)
      setReveal(withNames)
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!name.trim()) return
    onError(null)
    try {
      await api.savedQueryCreate({
        name: name.trim(),
        definition: draft.definition,
        group_by: draft.group_by,
      })
      setName('')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      onError(errorMessage(e))
    }
  }

  return (
    <>
      <div className="card">
        <h3>{t('builder.title')}</h3>
        <QueryBuilder value={draft} onChange={setDraft} onError={onError} />

        <div className="btn-row" style={{ marginTop: 14 }}>
          <button className="btn" onClick={() => run(reveal)}
                  disabled={busy || !ready}>
            {busy ? t('analytics.running') : t('builder.preview')}
          </button>
        </div>
      </div>

      <QueryResult result={result} reveal={reveal}
                   onToggleReveal={() => run(!reveal)} />

      {result && (
        <div className="card">
          <h3>{t('builder.save')}</h3>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end',
                        flexWrap: 'wrap' }}>
            <div className="field" style={{ flex: 1, minWidth: 240,
                                            marginBottom: 0 }}>
              <label>{t('builder.queryName')}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <button className="btn" onClick={save} disabled={!name.trim()}>
              {t('builder.save')}
            </button>
            {saved && <span className="badge badge-ok">{t('builder.saved')}</span>}
          </div>
        </div>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ saved */

function SavedQueries({ onError }) {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState([])
  const [result, setResult] = useState(null)
  const [activeId, setActiveId] = useState(null)
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.savedQueries()
      .then((r) => setRows(r.data.data))
      .catch((e) => onError(errorMessage(e)))
  }, [onError])

  useEffect(() => { load() }, [load])

  const run = async (id, withNames) => {
    setBusy(true)
    onError(null)
    try {
      const r = await api.savedQueryRun(id, withNames, lang)
      setResult(r.data)
      setActiveId(id)
      setReveal(withNames)
      load()
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm(t('builder.deleteWarn'))) return
    try {
      await api.savedQueryDelete(id)
      if (activeId === id) { setResult(null); setActiveId(null) }
      load()
    } catch (e) {
      onError(errorMessage(e))
    }
  }

  return (
    <>
      <div className="card flush">
        <div style={{ padding: '11px 14px',
                      borderBottom: '1px solid var(--slate-200)',
                      fontWeight: 620, fontSize: 13 }}>
          {t('builder.savedQueries')} <span className="muted">({rows.length})</span>
        </div>
        {rows.length === 0 ? (
          <div className="empty">{t('builder.noSaved')}</div>
        ) : (
          <table>
            <thead><tr>
              <th className="col-grow">{t('builder.queryName')}</th>
              <th className="col-shrink num">{t('analytics.answer')}</th>
              <th className="col-shrink">{t('builder.lastRun')}</th>
              <th className="col-shrink">{t('audit.user')}</th>
              <th className="col-actions" />
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    <div className="muted" style={{ fontSize: 11.5 }}>
                      {r.summary}
                    </div>
                  </td>
                  <td className="num">
                    {r.last_run_count != null
                      ? <strong>{r.last_run_count}</strong> : '—'}
                  </td>
                  <td className="mono muted" style={{ fontSize: 11.5 }}>
                    {r.last_run_at
                      ? r.last_run_at.slice(0, 16).replace('T', ' ') : '—'}
                  </td>
                  <td className="muted">{r.created_by}</td>
                  <td>
                    <div className="btn-row">
                      <button className="btn btn-sm" disabled={busy}
                              onClick={() => run(r.id, false)}>
                        {t('builder.run')}
                      </button>
                      {r.mine !== false && (
                        <button className="btn btn-danger btn-sm"
                                onClick={() => remove(r.id)}>×</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <QueryResult result={result} reveal={reveal}
                   onToggleReveal={() => activeId && run(activeId, !reveal)} />
    </>
  )
}
