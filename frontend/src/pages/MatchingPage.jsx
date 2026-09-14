import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'

export default function MatchingPage() {
  const { t, pick } = useI18n()
  const [vacancies, setVacancies] = useState([])
  const [vacancyId, setVacancyId] = useState('')
  const [runId, setRunId] = useState(null)
  const [results, setResults] = useState(null)
  const [reveal, setReveal] = useState(false)
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.vacancies().then((r) => setVacancies(r.data.data))
      .catch((e) => setError(errorMessage(e)))
  }, [])

  const run = async () => {
    if (!vacancyId) return
    setBusy(true); setError(null); setSelected(null); setResults(null)
    try {
      const r = await api.runMatching({ vacancy_id: Number(vacancyId) })
      setRunId(r.data.id)
      const res = await api.matchingResults(r.data.id, false)
      setResults(res.data)
      setReveal(false)
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  const toggleReveal = async () => {
    if (!runId) return
    const next = !reveal
    try {
      const res = await api.matchingResults(runId, next)
      setResults(res.data)
      setReveal(next)
      if (selected) {
        const all = [...res.data.shortlist, ...res.data.potential_after_development]
        setSelected(all.find((x) => x.id === selected.id) || null)
      }
    } catch (e) { setError(errorMessage(e)) }
  }

  const chosen = vacancies.find((v) => v.id === Number(vacancyId))

  return (
    <>
      <h2>{t('matching.title')}</h2>

      {error && <div className="alert alert-bad">{error}</div>}

      <div className="card">
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="field" style={{ flex: 1, minWidth: 260, marginBottom: 0 }}>
            <label>{t('matching.selectVacancy')}</label>
            <select value={vacancyId} onChange={(e) => setVacancyId(e.target.value)}>
              <option value="">—</option>
              {vacancies.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title} ({v.total_weight}/100)
                </option>
              ))}
            </select>
          </div>
          <button className="btn" onClick={run}
                  disabled={busy || !vacancyId || (chosen && chosen.total_weight !== 100)}>
            {busy ? t('matching.running') : t('matching.run')}
          </button>
        </div>
        {chosen && chosen.total_weight !== 100 && (
          <div className="alert alert-warn" style={{ marginTop: 12, marginBottom: 0 }}>
            {t('vacancy.weightError')} ({chosen.total_weight})
          </div>
        )}
      </div>

      {!results ? (
        <div className="card"><div className="empty">{t('matching.noRun')}</div></div>
      ) : (
        <>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between',
                          gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div className="muted" style={{ fontSize: 12.5 }}>
                {t('matching.model')} {results.scoring_model} ·
                {' '}v{results.requirements_version} ·
                {' '}{t('matching.evaluated')}: {results.total_evaluated} ·
                {' '}{t('matching.qualified')}: {results.total_qualified}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={toggleReveal}>
                {reveal ? t('matching.hideNames') : t('matching.revealNames')}
              </button>
            </div>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
              {t('matching.revealHint')}
            </div>
          </div>

          <div className="split">
            <div>
              <ResultList title={t('matching.shortlist')} rows={results.shortlist}
                          selected={selected} onSelect={setSelected} t={t} />
              {results.potential_after_development.length > 0 && (
                <ResultList title={t('matching.potential')}
                            rows={results.potential_after_development}
                            selected={selected} onSelect={setSelected} t={t} muted />
              )}
            </div>

            <div>
              {selected
                ? <CalculationCard row={selected} t={t} pick={pick}
                    onDecision={async (body) => {
                      try {
                        await api.recordDecision(selected.id, body)
                        const res = await api.matchingResults(runId, reveal)
                        setResults(res.data)
                        const all = [...res.data.shortlist,
                                     ...res.data.potential_after_development]
                        setSelected(all.find((x) => x.id === selected.id) || null)
                      } catch (e) { setError(errorMessage(e)) }
                    }} />
                : <div className="card"><div className="empty">
                    {t('matching.explanation')}
                  </div></div>}
            </div>
          </div>
        </>
      )}
    </>
  )
}

function ResultList({ title, rows, selected, onSelect, t, muted }) {
  return (
    <div className="card flush" style={{ opacity: muted ? 0.92 : 1 }}>
      <div style={{ padding: '11px 14px', borderBottom: '1px solid var(--slate-200)',
                    fontWeight: 620, fontSize: 13 }}>
        {title} <span className="muted">({rows.length})</span>
      </div>
      <div className="list">
        {rows.length === 0 && <div className="empty">{t('common.none')}</div>}
        {rows.map((r) => (
          <div key={r.id}
               className={`list-row ${selected?.id === r.id ? 'active' : ''}`}
               onClick={() => onSelect(r)}>
            <div>
              <div className="list-title">
                {r.system_rank}. {r.display_name}
              </div>
              <div className="list-sub">
                {r.readiness_code || '—'}
                {r.decision && <> · <span className="badge badge-mute">
                  {r.decision.decision}</span></>}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="score-big" style={{
                fontSize: 18,
                color: r.is_qualified ? 'var(--accent)' : 'var(--bad)',
              }}>{r.score}%</div>
              {!r.is_qualified && (
                <span className="badge badge-bad">{t('matching.criticalFailures')}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function CalculationCard({ row, t, pick, onDecision }) {
  const { isAdmin } = useAuth()
  const e = row.explanation
  const [decision, setDecision] = useState('selected')
  const [finalRank, setFinalRank] = useState(row.system_rank)
  const [reason, setReason] = useState('')

  useEffect(() => {
    setFinalRank(row.system_rank)
    setReason(row.decision?.reason || '')
    setDecision(row.decision?.decision || 'selected')
  }, [row.id, row.system_rank, row.decision])

  const diverges = Number(finalRank) !== row.system_rank
  const canSubmit = !diverges || reason.trim().length > 0

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ marginBottom: 2 }}>{row.display_name}</h3>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {t('matching.rank')} {row.system_rank} · {row.readiness_code || '—'}
            </div>
          </div>
          <div className="score-big"
               style={{ color: row.is_qualified ? 'var(--accent)' : 'var(--bad)' }}>
            {row.score}%
          </div>
        </div>

        {!row.is_qualified && (
          <div className="alert alert-bad" style={{ marginTop: 14, marginBottom: 0 }}>
            <strong>{t('matching.criticalFailures')}</strong>
            {e.critical_failures.map((c, i) => (
              <div key={i}>· {c.requirement} — {c.detail}</div>
            ))}
          </div>
        )}
      </div>

      <div className="card flush">
        <table>
          <thead><tr>
            <th>{t('matching.requirement')}</th>
            <th>{t('matching.fact')}</th>
            <th className="num">M</th>
            <th className="num">{t('common.weight')}</th>
            <th className="num">{t('matching.contribution')}</th>
            <th>{t('common.status')}</th>
          </tr></thead>
          <tbody>
            {e.requirements.map((r, i) => (
              <tr key={i} className={`req-row ${r.status}`}>
                <td>
                  <strong>{pick(r, 'label')}</strong>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {t(`vacancy.crit.${r.criticality}`)}
                  </div>
                </td>
                <td className="muted">{r.fact}</td>
                <td className="num">{r.m}</td>
                <td className="num">{r.weight}</td>
                <td className="num"><strong>{r.contribution}</strong></td>
                <td>
                  <span className={`badge ${
                    r.status === 'met' ? 'badge-ok'
                      : r.status === 'gap' ? 'badge-bad'
                      : r.status === 'compensated' ? 'badge-conf' : 'badge-warn'}`}>
                    {t(`matching.statusLabel.${r.status}`) || r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4} style={{ textAlign: 'right', fontWeight: 600 }}>
                {t('matching.score')}
              </td>
              <td className="num"><strong>{row.score}</strong></td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      {e.gaps?.length > 0 && (
        <div className="card">
          <h3>{t('matching.gaps')}</h3>
          {e.gaps.map((g, i) => (
            <div key={i} style={{ fontSize: 13, marginBottom: 4 }}>
              · <strong>{g.requirement}</strong> — <span className="muted">{g.detail}</span>
            </div>
          ))}
        </div>
      )}

      {isAdmin && (
      <div className="card">
        <h3>{t('matching.decision')}</h3>
        <div className="form-row-3">
          <div className="field">
            <label>{t('matching.decision')}</label>
            <select value={decision} onChange={(ev) => setDecision(ev.target.value)}>
              <option value="selected">selected</option>
              <option value="rejected">rejected</option>
              <option value="on_hold">on_hold</option>
              <option value="reserve">reserve</option>
            </select>
          </div>
          <div className="field">
            <label>{t('matching.rank')}</label>
            <input type="number" value={finalRank}
                   onChange={(ev) => setFinalRank(ev.target.value)} />
          </div>
          <div className="field">
            <label>{t('audit.reason')}</label>
            <input value={reason} onChange={(ev) => setReason(ev.target.value)}
                   placeholder={diverges ? t('matching.decisionReasonRequired') : ''} />
          </div>
        </div>
        {diverges && !reason.trim() && (
          <div className="alert alert-warn">{t('matching.decisionReasonRequired')}</div>
        )}
        <button className="btn" disabled={!canSubmit}
                onClick={() => onDecision({
                  decision, final_rank: Number(finalRank),
                  reason: reason || null, decided_by: 'hr_analyst',
                })}>
          {t('common.save')}
        </button>
      </div>
      )}
    </>
  )
}
