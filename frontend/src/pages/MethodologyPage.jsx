import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

export default function MethodologyPage() {
  const { t, pick } = useI18n()
  const [models, setModels] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [model, setModel] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const loadModels = useCallback(() => {
    api.scoringModels().then((r) => {
      setModels(r.data)
      if (!activeId && r.data.length) {
        setActiveId((r.data.find((m) => m.is_default) || r.data[0]).id)
      }
    }).catch((e) => setError(errorMessage(e)))
  }, [activeId])

  useEffect(() => { loadModels() }, [loadModels])

  const loadModel = useCallback(() => {
    if (!activeId) return
    api.scoringModel(activeId).then((r) => setModel(r.data))
      .catch((e) => setError(errorMessage(e)))
  }, [activeId])

  useEffect(() => { loadModel() }, [loadModel])

  const clone = async () => {
    const version = window.prompt(t('methodology.version'), '')
    if (!version) return
    setError(null)
    try {
      const r = await api.modelClone(activeId, version)
      setNotice(t('common.saved'))
      loadModels()
      setActiveId(r.data.id)
    } catch (e) { setError(errorMessage(e)) }
  }

  const approve = async () => {
    setError(null)
    try {
      await api.modelApprove(activeId, true)
      setNotice(t('common.saved'))
      loadModels(); loadModel()
    } catch (e) { setError(errorMessage(e)) }
  }

  const locked = model?.status === 'approved'

  return (
    <>
      <h2>{t('methodology.title')}</h2>
      <p className="page-hint">{t('methodology.hint')}</p>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="split">
        <div className="card flush">
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--slate-200)' }}>
            <strong style={{ fontSize: 13 }}>{t('methodology.models')}</strong>
          </div>
          <div className="list">
            {models.map((m) => (
              <div key={m.id} className={`list-row ${activeId === m.id ? 'active' : ''}`}
                   onClick={() => setActiveId(m.id)}>
                <div>
                  <div className="list-title">{m.version} — {m.name}</div>
                  <div className="list-sub">
                    {t(`methodology.modelStatus.${m.status}`)}
                    {m.is_default && ` · ${t('methodology.default')}`}
                  </div>
                </div>
                <span className={`badge ${m.status === 'approved'
                  ? 'badge-ok' : 'badge-warn'}`}>{m.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          {!model ? <div className="spinner" /> : (
            <>
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between',
                              gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ marginBottom: 2 }}>{model.version} — {model.name}</h3>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      {t('common.status')}: {t(`methodology.modelStatus.${model.status}`)}
                      {model.approved_by && ` · ${model.approved_by}`}
                    </div>
                  </div>
                  <div className="btn-row">
                    <button className="btn btn-ghost btn-sm" onClick={clone}>
                      {t('methodology.clone')}
                    </button>
                    {model.status !== 'approved' && (
                      <button className="btn btn-sm" onClick={approve}>
                        {t('methodology.approve')}
                      </button>
                    )}
                  </div>
                </div>
                {locked && (
                  <div className="alert alert-info" style={{ marginTop: 12, marginBottom: 0 }}>
                    {t('methodology.approvedImmutable')}
                  </div>
                )}
              </div>

              <FunctionsCard model={model} locked={locked} t={t} pick={pick}
                             onChanged={loadModel} onError={setError} />
              <CompensationsCard model={model} locked={locked} t={t} pick={pick}
                                 onChanged={loadModel} onError={setError} />
              <BandsCard model={model} locked={locked} t={t} pick={pick}
                         onChanged={loadModel} onError={setError} />
            </>
          )}
        </div>
      </div>
    </>
  )
}

function FunctionsCard({ model, locked, t, pick, onChanged, onError }) {
  return (
    <div className="card flush">
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--slate-200)' }}>
        <strong style={{ fontSize: 14 }}>{t('methodology.functions')}</strong>
      </div>
      <table>
        <thead><tr>
          <th>{t('common.name')}</th>
          <th>{t('methodology.kind')}</th>
          <th>{t('methodology.breakpoints')}</th>
          <th style={{ width: 90 }} />
        </tr></thead>
        <tbody>
          {model.functions.length === 0 && (
            <tr><td colSpan={4} className="empty">{t('common.none')}</td></tr>
          )}
          {model.functions.map((f) => (
            <EditableJsonRow key={f.id} row={f} locked={locked} t={t} pick={pick}
              jsonField="breakpoints" extraCell={f.kind}
              onSave={(value) => api.functionUpdate(f.id, {
                code: f.code, name_ru: f.name_ru, name_kk: f.name_kk,
                name_en: f.name_en, kind: f.kind, breakpoints: value,
              })}
              onChanged={onChanged} onError={onError} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CompensationsCard({ model, locked, t, pick, onChanged, onError }) {
  return (
    <div className="card flush">
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--slate-200)' }}>
        <strong style={{ fontSize: 14 }}>{t('methodology.compensations')}</strong>
      </div>
      <table>
        <thead><tr>
          <th>{t('common.name')}</th>
          <th />
          <th>entries</th>
          <th style={{ width: 90 }} />
        </tr></thead>
        <tbody>
          {model.compensations.length === 0 && (
            <tr><td colSpan={4} className="empty">{t('common.none')}</td></tr>
          )}
          {model.compensations.map((c) => (
            <EditableJsonRow key={c.id} row={c} locked={locked} t={t} pick={pick}
              jsonField="entries" extraCell=""
              onSave={(value) => api.compensationUpdate(c.id, {
                code: c.code, name_ru: c.name_ru, name_kk: c.name_kk,
                name_en: c.name_en, entries: value,
              })}
              onChanged={onChanged} onError={onError} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BandsCard({ model, locked, t, pick, onChanged, onError }) {
  return (
    <div className="card flush">
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--slate-200)' }}>
        <strong style={{ fontSize: 14 }}>{t('methodology.readiness')}</strong>
      </div>
      <table>
        <thead><tr>
          <th>{t('common.code')}</th>
          <th>{t('common.name')}</th>
          <th className="num">{t('methodology.minScore')}</th>
        </tr></thead>
        <tbody>
          {model.readiness_bands.map((b) => (
            <tr key={b.id}>
              <td className="mono">{b.code}</td>
              <td>
                <span className="badge" style={{
                  background: (b.color || '#eee') + '22',
                  color: b.color || 'var(--slate-600)',
                }}>{pick(b)}</span>
              </td>
              <td className="num"><strong>{b.min_score}</strong></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A row whose JSON payload can be edited in place — this is where the
 *  methodologist changes M-values without a code release. */
function EditableJsonRow({ row, locked, t, pick, jsonField, extraCell,
                          onSave, onChanged, onError }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(() => JSON.stringify(row[jsonField], null, 1))

  useEffect(() => { setText(JSON.stringify(row[jsonField], null, 1)) },
    [row, jsonField])

  const save = async () => {
    onError(null)
    let parsed
    try { parsed = JSON.parse(text) }
    catch { onError('Invalid JSON'); return }
    try {
      await onSave(parsed)
      setEditing(false)
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <tr>
      <td>
        <strong>{pick(row)}</strong>
        <div className="mono muted" style={{ fontSize: 11 }}>{row.code}</div>
      </td>
      <td className="muted">{extraCell}</td>
      <td>
        {editing ? (
          <textarea className="mono" value={text} rows={5}
                    onChange={(e) => setText(e.target.value)} />
        ) : (
          <code className="mono muted" style={{ fontSize: 11 }}>
            {JSON.stringify(row[jsonField])}
          </code>
        )}
      </td>
      <td>
        {locked ? <span className="muted" style={{ fontSize: 11 }}>🔒</span>
          : editing ? (
            <div className="btn-row">
              <button className="btn btn-sm" onClick={save}>{t('common.save')}</button>
              <button className="btn btn-ghost btn-sm"
                      onClick={() => setEditing(false)}>×</button>
            </div>
          ) : (
            <button className="btn btn-ghost btn-sm"
                    onClick={() => setEditing(true)}>{t('common.edit')}</button>
          )}
      </td>
    </tr>
  )
}
