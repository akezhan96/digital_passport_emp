import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import ConditionBuilder, { ConditionSummary } from '../components/ConditionBuilder'

const CRITICALITIES = ['critical', 'must', 'nice']

export default function VacanciesPage() {
  const { t, pick } = useI18n()
  const { isAdmin } = useAuth()
  const [vacancies, setVacancies] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [reqTypes, setReqTypes] = useState([])
  const [functions, setFunctions] = useState([])
  const [compensations, setCompensations] = useState([])
  const [countries, setCountries] = useState([])
  const [orgUnits, setOrgUnits] = useState([])
  const [profiles, setProfiles] = useState([])
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [refCatalogs, setRefCatalogs] = useState({})

  const loadVacancies = useCallback(() => {
    api.vacancies().then((r) => setVacancies(r.data.data))
      .catch((e) => setError(errorMessage(e)))
  }, [])

  useEffect(() => {
    loadVacancies()
    api.refList('requirement-types').then((r) => setReqTypes(r.data.data)).catch(() => {})
    api.refList('countries').then((r) => setCountries(r.data.data)).catch(() => {})
    api.refList('org-units').then((r) => setOrgUnits(r.data.data)).catch(() => {})
    api.profiles().then((r) => setProfiles(r.data)).catch(() => {})
    // Catalogues used to render stored conditions as readable text.
    Promise.all(['job-families', 'languages', 'language-levels', 'org-unit-types',
                 'competencies', 'education-levels', 'education-fields', 'countries']
      .map((c) => api.refList(c).then((r) => [c, r.data.data]).catch(() => [c, []])))
      .then((pairs) => setRefCatalogs(Object.fromEntries(pairs)))
    api.scoringModels().then(async (r) => {
      const def = r.data.find((m) => m.is_default) || r.data[0]
      if (!def) return
      const full = await api.scoringModel(def.id)
      setFunctions(full.data.functions)
      setCompensations(full.data.compensations)
    }).catch(() => {})
  }, [loadVacancies])

  const loadDetail = useCallback((id) => {
    if (!id) return
    api.vacancy(id).then((r) => setDetail(r.data)).catch((e) => setError(errorMessage(e)))
  }, [])

  useEffect(() => { loadDetail(selected) }, [selected, loadDetail])

  const totalWeight = detail ? detail.requirements.reduce((s, r) => s + r.weight, 0) : 0
  const balanced = totalWeight === 100

  const approve = async () => {
    setError(null); setNotice(null)
    try {
      await api.vacancyUpdate(selected, { status: 'active' })
      setNotice(t('common.saved'))
      loadDetail(selected); loadVacancies()
    } catch (e) { setError(errorMessage(e)) }
  }

  return (
    <>
      <h2>{t('vacancy.title')}</h2>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="split">
        <div>
          {isAdmin && (
            <div className="card">
              <button className="btn" style={{ width: '100%' }}
                      onClick={() => setShowCreate(!showCreate)}>
                {showCreate ? t('common.cancel') : t('vacancy.add')}
              </button>
            </div>
          )}

          {isAdmin && showCreate && (
            <CreateVacancy t={t} pick={pick} countries={countries}
              orgUnits={orgUnits} profiles={profiles} onError={setError}
              onDone={(id) => { setShowCreate(false); loadVacancies(); setSelected(id) }} />
          )}

          <div className="card flush">
            <div className="list">
              {vacancies.length === 0 && <div className="empty">{t('common.none')}</div>}
              {vacancies.map((v) => (
                <div key={v.id}
                     className={`list-row ${selected === v.id ? 'active' : ''}`}
                     onClick={() => setSelected(v.id)}>
                  <div>
                    <div className="list-title">{v.title}</div>
                    <div className="list-sub">
                      {v.country_name_ru} · {v.requirements_count} {t('vacancy.requirements')}
                    </div>
                  </div>
                  <span className={`badge ${v.total_weight === 100
                    ? 'badge-ok' : 'badge-warn'}`}>{v.total_weight}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          {!detail ? (
            <div className="card"><div className="empty">{t('common.select')}</div></div>
          ) : (
            <>
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between',
                              alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <h3 style={{ marginBottom: 4 }}>{detail.title}</h3>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      {t('common.status')}: {detail.status} ·
                      {' '}v{detail.requirements_version}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className={balanced ? 'badge badge-ok' : 'badge badge-bad'}>
                      {t('vacancy.totalWeight')}: {totalWeight} / 100
                    </div>
                    {isAdmin && balanced && detail.status !== 'active' && (
                      <div><button className="btn btn-sm" style={{ marginTop: 8 }}
                                   onClick={approve}>{t('vacancy.approve')}</button></div>
                    )}
                  </div>
                </div>
                {!balanced && (
                  <div className="alert alert-warn" style={{ marginTop: 12, marginBottom: 0 }}>
                    {t('vacancy.weightError')}
                  </div>
                )}
              </div>

              <div className="card flush">
                <table>
                  <thead><tr>
                    <th>{t('vacancy.label')}</th>
                    <th>{t('vacancy.condition')}</th>
                    <th>{t('vacancy.criticality')}</th>
                    <th className="num">{t('common.weight')}</th>
                    <th>{t('vacancy.scoringFunction')}</th>
                    <th style={{ width: 90 }} />
                  </tr></thead>
                  <tbody>
                    {detail.requirements.length === 0 && (
                      <tr><td colSpan={6} className="empty">{t('common.none')}</td></tr>
                    )}
                    {detail.requirements.map((r) => (
                      <RequirementRow key={r.id} req={r} t={t} pick={pick}
                        functions={functions} reqTypes={reqTypes}
                        catalogs={refCatalogs} readOnly={!isAdmin}
                        onChanged={() => { loadDetail(selected); loadVacancies() }}
                        onError={setError} />
                    ))}
                  </tbody>
                </table>
              </div>

              {isAdmin && <AddRequirement vacancyId={selected} t={t} pick={pick}
                reqTypes={reqTypes} functions={functions} compensations={compensations}
                onError={setError}
                onDone={() => { loadDetail(selected); loadVacancies() }} />}
            </>
          )}
        </div>
      </div>
    </>
  )
}

/* ---------------------------------------------------------------- */

function RequirementRow({ req, t, pick, functions, reqTypes = [],
                          catalogs = {}, onChanged, onError, readOnly = false }) {
  const [weight, setWeight] = useState(req.weight)
  const [crit, setCrit] = useState(req.criticality)
  const [dirty, setDirty] = useState(false)

  useEffect(() => { setWeight(req.weight); setCrit(req.criticality); setDirty(false) },
    [req.weight, req.criticality])

  const save = async () => {
    onError(null)
    try {
      await api.requirementUpdate(req.id, { weight: Number(weight), criticality: crit })
      setDirty(false); onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  const remove = async () => {
    if (!window.confirm(t('common.confirmDelete'))) return
    try { await api.requirementDelete(req.id); onChanged() }
    catch (e) { onError(errorMessage(e)) }
  }

  const badgeClass = crit === 'critical' ? 'badge-bad'
    : crit === 'must' ? 'badge-warn' : 'badge-mute'
  const fn = functions.find((f) => f.id === req.scoring_function_id)

  return (
    <tr>
      <td>
        <strong>{pick(req, 'label')}</strong>
        {req.compensation_table_id && (
          <div><span className="badge badge-mute">{t('vacancy.compensation')}</span></div>
        )}
      </td>
      <td className="muted">
        <ConditionSummary
          schema={reqTypes.find((x) => x.id === req.requirement_type_id)
            ?.condition_schema}
          condition={req.condition} catalogs={catalogs} />
      </td>
      <td>
        {readOnly ? (
          <span className={`badge ${badgeClass}`}>{t(`vacancy.crit.${crit}`)}</span>
        ) : (
          <>
            <select value={crit} style={{ minWidth: 130 }}
                    onChange={(e) => { setCrit(e.target.value); setDirty(true) }}>
              {CRITICALITIES.map((c) => (
                <option key={c} value={c}>{t(`vacancy.crit.${c}`)}</option>
              ))}
            </select>
            <div><span className={`badge ${badgeClass}`}>
              {t(`vacancy.crit.${crit}`)}</span></div>
          </>
        )}
      </td>
      <td className="num">
        {readOnly ? <strong>{weight}</strong> : (
          <input type="number" value={weight} style={{ width: 70, textAlign: 'right' }}
                 onChange={(e) => { setWeight(e.target.value); setDirty(true) }} />
        )}
      </td>
      <td className="muted">{fn ? pick(fn) : '—'}</td>
      <td>
        {!readOnly && (
          <div className="btn-row">
            {dirty && (
              <button className="btn btn-sm" onClick={save}>{t('common.save')}</button>
            )}
            <button className="btn btn-danger btn-sm" onClick={remove}>×</button>
          </div>
        )}
      </td>
    </tr>
  )
}

function AddRequirement({ vacancyId, t, pick, reqTypes, functions, compensations,
                          onDone, onError }) {
  const [typeId, setTypeId] = useState(null)
  const [label, setLabel] = useState({ ru: '', kk: '', en: '' })
  const [condition, setCondition] = useState({})
  const [weight, setWeight] = useState(10)
  const [crit, setCrit] = useState('must')
  const [fnId, setFnId] = useState(null)
  const [compId, setCompId] = useState(null)
  const [showJson, setShowJson] = useState(false)

  const type = reqTypes.find((r) => r.id === typeId)

  /** Seed the condition with each field's default when the type changes. */
  const pickType = (id) => {
    setTypeId(id)
    const chosen = reqTypes.find((r) => r.id === id)
    const spec = chosen?.condition_schema?.fields || []
    const seed = {}
    spec.forEach((f) => {
      if (f.kind === 'list') seed[f.key] = []
      else if (f.default !== undefined) seed[f.key] = f.default
    })
    setCondition(seed)
  }

  const submit = async (ev) => {
    ev.preventDefault(); onError(null)
    // Drop empty optional entries so the stored condition stays clean.
    const cleaned = Object.fromEntries(
      Object.entries(condition).filter(([, v]) =>
        v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)))
    try {
      await api.requirementAdd(vacancyId, {
        requirement_type_id: typeId,
        label_ru: label.ru, label_kk: label.kk || null, label_en: label.en || null,
        condition: cleaned, weight: Number(weight), criticality: crit,
        scoring_function_id: fnId, compensation_table_id: compId,
      })
      setLabel({ ru: '', kk: '', en: '' }); setCondition({}); setWeight(10)
      onDone()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <div className="card">
      <h3>{t('vacancy.addRequirement')}</h3>
      <form onSubmit={submit}>
        <div className="form-row">
          <div className="field">
            <label>{t('vacancy.requirementType')}</label>
            <select value={typeId ?? ''} required
                    onChange={(e) => pickType(
                      e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {reqTypes.map((r) => <option key={r.id} value={r.id}>{pick(r)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>{t('common.weight')}</label>
            <input type="number" value={weight} required
                   onChange={(e) => setWeight(e.target.value)} />
          </div>
        </div>

        <div className="form-row-3">
          <div className="field">
            <label>{t('vacancy.label')} (RU)</label>
            <input value={label.ru} required
                   onChange={(e) => setLabel({ ...label, ru: e.target.value })} />
          </div>
          <div className="field">
            <label>{t('vacancy.label')} (KK)</label>
            <input value={label.kk}
                   onChange={(e) => setLabel({ ...label, kk: e.target.value })} />
          </div>
          <div className="field">
            <label>{t('vacancy.label')} (EN)</label>
            <input value={label.en}
                   onChange={(e) => setLabel({ ...label, en: e.target.value })} />
          </div>
        </div>

        <div className="field">
          <label>{t('condition.title')}</label>
          <div style={{ border: '1px solid var(--slate-200)', borderRadius: 6,
                        padding: '14px 16px', background: '#fff' }}>
            <ConditionBuilder schema={type?.condition_schema}
                              value={condition} onChange={setCondition} />
          </div>

          {type && (
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm"
                      onClick={() => setShowJson(!showJson)}>
                {showJson ? t('condition.hideJson') : t('condition.showJson')}
              </button>
              {showJson && (
                <pre className="mono muted" style={{ fontSize: 11, marginTop: 6,
                     background: 'var(--slate-50)', padding: 10, borderRadius: 4,
                     overflowX: 'auto' }}>
{JSON.stringify(condition, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>

        <div className="form-row-3">
          <div className="field">
            <label>{t('vacancy.criticality')}</label>
            <select value={crit} onChange={(e) => setCrit(e.target.value)}>
              {CRITICALITIES.map((c) => (
                <option key={c} value={c}>{t(`vacancy.crit.${c}`)}</option>
              ))}
            </select>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
              {t(`vacancy.critHint.${crit}`)}
            </div>
          </div>
          <div className="field">
            <label>{t('vacancy.scoringFunction')}</label>
            <select value={fnId ?? ''}
                    onChange={(e) => setFnId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {functions.map((f) => <option key={f.id} value={f.id}>{pick(f)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>{t('vacancy.compensation')}</label>
            <select value={compId ?? ''}
                    onChange={(e) => setCompId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">—</option>
              {compensations.map((c) => <option key={c.id} value={c.id}>{pick(c)}</option>)}
            </select>
          </div>
        </div>

        <button className="btn" type="submit">{t('common.add')}</button>
      </form>
    </div>
  )
}

function CreateVacancy({ t, pick, countries, orgUnits, profiles, onDone, onError }) {
  const [form, setForm] = useState({ title: '', country_id: null, org_unit_id: null,
    profile_id: null, description: '' })

  const submit = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      const r = await api.vacancyCreate(form)
      onDone(r.data.id)
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <div className="card">
      <h3>{t('vacancy.add')}</h3>
      <form onSubmit={submit}>
        <div className="field">
          <label>{t('vacancy.name')}</label>
          <input value={form.title} required
                 onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div className="field">
          <label>{t('vacancy.country')}</label>
          <select value={form.country_id ?? ''} required
                  onChange={(e) => setForm({ ...form, country_id: Number(e.target.value) })}>
            <option value="">—</option>
            {countries.map((c) => <option key={c.id} value={c.id}>{pick(c)}</option>)}
          </select>
        </div>
        <div className="field">
          <label>{t('vacancy.orgUnit')}</label>
          <select value={form.org_unit_id ?? ''}
                  onChange={(e) => setForm({ ...form,
                    org_unit_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">—</option>
            {orgUnits.map((o) => <option key={o.id} value={o.id}>{pick(o)}</option>)}
          </select>
        </div>
        <div className="field">
          <label>{t('vacancy.profile')}</label>
          <select value={form.profile_id ?? ''}
                  onChange={(e) => setForm({ ...form,
                    profile_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">—</option>
            {profiles.map((p) => <option key={p.id} value={p.id}>{pick(p)}</option>)}
          </select>
        </div>
        <button className="btn" type="submit">{t('common.save')}</button>
      </form>
    </div>
  )
}
