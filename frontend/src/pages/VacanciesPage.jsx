import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { candidateApi } from '../candidateApi'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { vacancyText } from '../i18n/vacancyMethodology'
import { recruitmentText } from '../i18n/recruitment'
import { recruitmentQuery } from '../recruitment'
import RecruitmentSummary from '../components/RecruitmentSummary'
import WorklistPager from '../components/WorklistPager'
import ConditionBuilder, { ConditionSummary } from '../components/ConditionBuilder'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { confirmUnsavedLeave } from '../unsavedChanges'
import './worklists.css'

const CRITICALITIES = ['critical', 'must', 'nice']
const VACANCY_SCOPE = 'vacancy-form'

export default function VacanciesPage() {
  const { t, pick, lang } = useI18n()
  const l = vacancyText(lang)
  const c = recruitmentText(lang)
  const { isAdmin } = useAuth()
  const [vacancies, setVacancies] = useState([])
  const [selected, setSelected] = useState(() => recruitmentQuery().vacancy)
  const [detail, setDetail] = useState(null)
  const [models, setModels] = useState([])
  const [countries, setCountries] = useState([])
  const [orgUnits, setOrgUnits] = useState([])
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [reqTypes, setReqTypes] = useState([])
  const [functions, setFunctions] = useState([])
  const [compensations, setCompensations] = useState([])
  const [refCatalogs, setRefCatalogs] = useState({})
  const loadVacancies = useCallback(() => { api.vacancies().then(r => setVacancies(r.data.data)).catch(e => setError(errorMessage(e))) }, [])
  useEffect(() => {
    loadVacancies()
    Promise.all([candidateApi.models(), api.refList('countries'), api.refList('org-units')]).then(([m,c,o]) => {
      setModels(m.data.filter(row => row.status !== 'draft')); setCountries(c.data.data); setOrgUnits(o.data.data)
    }).catch(e => setError(errorMessage(e)))
  }, [loadVacancies, refresh])
  useEffect(() => {
    if (!selected) { setDetail(null); return }
    let active = true; setDetail(null)
    api.vacancy(selected).then(r => { if (active) setDetail(r.data) }).catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false }
  }, [selected, refresh])
  useEffect(() => {
    if (!detail || detail.candidate_methodology_id) return
    let active = true
    api.refList('requirement-types').then(r => { if (active) setReqTypes(r.data.data) }).catch(() => {})
    Promise.all(['job-families','languages','language-levels','org-unit-types','competencies','education-levels','education-fields','countries'].map(c =>
      api.refList(c).then(r => [c,r.data.data]).catch(() => [c,[]]))).then(pairs => { if (active) setRefCatalogs(Object.fromEntries(pairs)) })
    api.scoringModels().then(async r => { const selected = r.data.find(m => m.is_default); if (!selected) return
      const full = await api.scoringModel(selected.id); if (active) { setFunctions(full.data.functions); setCompensations(full.data.compensations) }
    }).catch(() => {})
    return () => { active = false }
  }, [detail?.id, detail?.candidate_methodology_id])
  const choose = id => { if (!confirmUnsavedLeave(VACANCY_SCOPE)) return; setSelected(id); setEditing(false); setCreating(false); setError(null) }
  const changed = () => setRefresh(value => value + 1)
  const filtered = vacancies.filter(v => (!status || v.status === status) &&
    [v.title,v.title_kk,v.country_name_ru,v.country_name_kk].some(value => (value || '').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())))
  const title = row => lang === 'kk' ? row.title_kk || row.title : row.title
  return <>
    <div className="worklist-toolbar" style={{ justifyContent: 'space-between', marginBottom: 14 }}><h2 style={{ margin: 0 }}>{t('vacancy.title')}</h2>
      {isAdmin && <button className="btn" onClick={() => { if (!confirmUnsavedLeave(VACANCY_SCOPE)) return; setCreating(true); setEditing(false); setError(null) }}>{l.create}</button>}</div>
    {error && <div className="alert alert-bad">{error}</div>}
    <div className="vacancy-workspace">
      <section className="card flush"><div className="worklist-toolbar">
        <input aria-label={l.search} type="search" placeholder={l.search} value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }} />
        <select aria-label={t('common.status')} value={status} onChange={e => { setStatus(e.target.value); setOffset(0) }}><option value="">{l.all}</option>
          {['draft','active','closed'].map(value => <option key={value} value={value}>{l[value]}</option>)}</select></div>
        <div className="list">{filtered.slice(offset,offset+10).map(row => <button key={row.id} className={`list-row worklist-select ${selected === row.id ? 'active' : ''}`} onClick={() => choose(row.id)}>
          <div><strong>{title(row)}</strong><small className="muted">{pick(row,'country_name')} <span className={`badge ${row.status === 'closed' ? 'badge-closed' : row.status === 'draft' ? 'badge-warn' : 'badge-ok'}`}>{l[row.status] || row.status}</span></small>
            <small className="muted">{row.candidate_methodology_id ? `${l.method} · v${row.methodology_version} · ≥ ${row.min_candidate_percent}%` : l.legacy}</small></div></button>)}
          {!filtered.length && <div className="empty">{l.empty}</div>}</div>
        <WorklistPager total={filtered.length} offset={offset} limit={10} onChange={setOffset} /></section>
      <section>
        {creating || (editing && detail) ? <VacancyForm key={creating ? 'new' : detail.id} initial={creating ? null : detail} models={models} countries={countries} units={orgUnits}
          onError={setError} onCancel={() => { if (confirmUnsavedLeave(VACANCY_SCOPE)) { setCreating(false); setEditing(false) } }}
          onDone={id => { setCreating(false); setEditing(false); setSelected(id); changed() }} />
          : !detail ? <div className="card"><div className="empty">{l.choose}</div></div> : <>
            <div className="card"><div className="worklist-toolbar" style={{ justifyContent: 'space-between' }}><h3 style={{ margin: 0 }}>{title(detail)}</h3>
              {isAdmin && <button className="btn btn-sm" onClick={() => setEditing(true)}>{l.edit}</button>}</div>
              <div className="recruitment-vacancy-meta"><span className={`badge ${detail.status === 'closed' ? 'badge-closed' : detail.status === 'draft' ? 'badge-warn' : 'badge-ok'}`}>{l[detail.status] || detail.status}</span><span><strong>{t('vacancy.country')}:</strong> {pick(countries.find(c => c.id === detail.country_id)) || '—'}</span><span><strong>{t('vacancy.orgUnit')}:</strong> {pick(orgUnits.find(unit => unit.id === detail.org_unit_id)) || c.noUnit}</span></div>
              {detail.methodology ? <><p className="recruitment-context"><strong>{pick(detail.methodology)}</strong> · v{detail.methodology.version} · ≥ {detail.min_candidate_percent}%</p>
                <details className="recruitment-conditions"><summary>{c.settings}</summary><p className="muted">{detail.requires_technical_profile ? l.technical : l.anyProfile}</p>
                  <div className="worklist-table-scroll"><table><thead><tr><th>№</th><th>{l.indicator}</th><th className="num">{l.maximum}</th></tr></thead>
                  <tbody>{detail.methodology.criteria.filter(c => c.enabled).map((c, index) => <tr key={c.id}><td>{index + 1}</td><td>{pick(c)}</td><td className="num">{c.max_points}</td></tr>)}</tbody></table></div></details></>
                : <p className="muted">{l.legacy} · {t('vacancy.totalWeight')}: {detail.total_weight} / 100</p>}
              {(lang === 'kk' ? detail.description_kk || detail.description : detail.description) && <details className="recruitment-conditions"><summary>{c.description}</summary><p>{lang === 'kk' ? detail.description_kk || detail.description : detail.description}</p></details>}
            </div>
            <RecruitmentSummary key={detail.id} vacancy={detail} onChanged={changed} />
            {!detail.candidate_methodology_id && <><div className="card flush worklist-table-scroll"><table><thead><tr><th>{t('vacancy.label')}</th><th>{t('vacancy.condition')}</th><th>{t('vacancy.criticality')}</th><th>{t('common.weight')}</th><th>{t('vacancy.scoringFunction')}</th><th /></tr></thead>
              <tbody>{detail.requirements.map(req => <RequirementRow key={req.id} req={req} t={t} pick={pick} functions={functions} reqTypes={reqTypes} catalogs={refCatalogs}
                readOnly={!isAdmin} onChanged={changed} onError={setError} />)}</tbody></table></div>
              {isAdmin && <AddRequirement vacancyId={detail.id} t={t} pick={pick} reqTypes={reqTypes} functions={functions} compensations={compensations} onError={setError} onDone={changed} />}</>}
          </>}
      </section>
    </div>
  </>
}

function VacancyForm({ initial, models, countries, units, onDone, onError, onCancel }) {
  const { lang, pick, t } = useI18n(); const l = vacancyText(lang)
  const legacy = Boolean(initial && !initial.candidate_methodology_id)
  const [form, setForm] = useState(() => ({ title: initial?.title || '', title_kk: initial?.title_kk || '', description: initial?.description || '',
    description_kk: initial?.description_kk || '', country_id: initial?.country_id || '', org_unit_id: initial?.org_unit_id || '',
    candidate_methodology_id: initial ? initial.candidate_methodology_id || '' : models.find(m => m.status === 'active')?.id || '',
    min_candidate_percent: initial?.min_candidate_percent ?? 70, requires_technical_profile: initial?.requires_technical_profile || false, status: initial?.status || 'active' }))
  const [dirty, setDirty] = useState(false); const [busy, setBusy] = useState(false)
  const markSaved = useUnsavedChanges(dirty, l.discard, VACANCY_SCOPE)
  const change = (key,value) => { setForm(old => ({...old,[key]:value})); setDirty(true) }
  const submit = async event => { event.preventDefault(); setBusy(true); onError(null)
    const { candidate_methodology_id, ...values } = form
    const body = {...values,country_id:Number(form.country_id),org_unit_id:form.org_unit_id ? Number(form.org_unit_id) : null,
      ...(candidate_methodology_id ? {candidate_methodology_id:Number(candidate_methodology_id)} : {}),min_candidate_percent:Number(form.min_candidate_percent)}
    try { const response = initial ? await api.vacancyUpdate(initial.id,body) : await api.vacancyCreate(body); markSaved(); setDirty(false); onDone(response.data.id) }
    catch(error) { onError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <form className="card" onSubmit={submit}><h3>{initial ? l.edit : l.create}</h3>
    {!models.length && !legacy && <div className="alert alert-warn">{l.methodsEmpty}</div>}
    <div className="form-row">{[['title',l.titleRu],['title_kk',l.titleKk]].map(([key,label]) => <div className="field" key={key}><label htmlFor={`vacancy-${key}`}>{label}</label><input id={`vacancy-${key}`} required={key === 'title'} maxLength={200} value={form[key]} onChange={e => change(key,e.target.value)} /></div>)}</div>
    <div className="form-row"><div className="field"><label htmlFor="vacancy-country">{t('vacancy.country')}</label><select id="vacancy-country" required value={form.country_id} onChange={e => change('country_id',e.target.value)}><option value="">—</option>{countries.map(c => <option key={c.id} value={c.id}>{pick(c)}</option>)}</select></div>
      <div className="field"><label htmlFor="vacancy-unit">{t('vacancy.orgUnit')}</label><select id="vacancy-unit" value={form.org_unit_id} onChange={e => change('org_unit_id',e.target.value)}><option value="">—</option>{units.map(c => <option key={c.id} value={c.id}>{pick(c)}</option>)}</select></div></div>
    <div className="field"><label htmlFor="vacancy-method">{l.version}</label><select id="vacancy-method" required={!legacy} value={form.candidate_methodology_id} onChange={e => change('candidate_methodology_id',e.target.value)}><option value="">{legacy ? l.legacy : '—'}</option>{models.map(m => <option key={m.id} value={m.id}>{pick(m)} · v{m.version}</option>)}</select></div>
    <div className="form-row"><div className="field"><label htmlFor="vacancy-threshold">{l.threshold}</label><input id="vacancy-threshold" required type="number" min={0} max={100} step="0.01" disabled={legacy && !form.candidate_methodology_id} value={form.min_candidate_percent} onChange={e => change('min_candidate_percent',e.target.value)} /></div>
      <div className="field"><label htmlFor="vacancy-status">{t('common.status')}</label><select id="vacancy-status" value={form.status} onChange={e => change('status',e.target.value)}>{['draft','active','closed','requirements_approved'].map(code => <option key={code} value={code}>{l[code]}</option>)}</select></div></div>
    <label className="checkbox"><input type="checkbox" checked={form.requires_technical_profile} onChange={e => change('requires_technical_profile',e.target.checked)} /> {l.technical}</label>
    <div className="form-row" style={{ marginTop: 14 }}>{[['description',l.descriptionRu],['description_kk',l.descriptionKk]].map(([key,label]) => <div className="field" key={key}><label htmlFor={`vacancy-${key}`}>{label}</label><textarea id={`vacancy-${key}`} rows={3} value={form[key]} onChange={e => change(key,e.target.value)} /></div>)}</div>
    {form.candidate_methodology_id && <p className="muted">{l.savedOnly}</p>}<div className="worklist-toolbar"><button className="btn" disabled={busy || (!models.length && !legacy)}>{t('common.save')}</button><button className="btn btn-ghost" type="button" onClick={onCancel} disabled={busy}>{t('common.cancel')}</button></div>
  </form>
}

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
      <td className="col-wrap">
        <strong>{pick(req, 'label')}</strong>
        {req.compensation_table_id && (
          <div><span className="badge badge-mute">{t('vacancy.compensation')}</span></div>
        )}
      </td>
      <td className="muted col-wrap">
        <ConditionSummary
          schema={reqTypes.find((x) => x.id === req.requirement_type_id)
            ?.condition_schema}
          condition={req.condition} catalogs={catalogs} />
      </td>
      <td>
        {readOnly ? (
          <span className={`badge ${badgeClass}`}>{t(`vacancy.crit.${crit}`)}</span>
        ) : (
          // The select already shows the value; a badge repeating it underneath
          // said the same word twice. It keeps the colour, not the duplication.
          <select value={crit} className={`select-${crit}`}
                  onChange={(e) => { setCrit(e.target.value); setDirty(true) }}>
            {CRITICALITIES.map((c) => (
              <option key={c} value={c}>{t(`vacancy.crit.${c}`)}</option>
            ))}
          </select>
        )}
      </td>
      <td className="num">
        {readOnly ? <strong>{weight}</strong> : (
          <input type="number" value={weight} min="0" max="100"
                 onChange={(e) => { setWeight(e.target.value); setDirty(true) }} />
        )}
      </td>
      <td className="muted col-wrap">{fn ? pick(fn) : '—'}</td>
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
        </div>

        <div className="field">
          <label>{t('condition.title')}</label>
          <div style={{ border: '1px solid var(--slate-200)', borderRadius: 6,
                        padding: '14px 16px', background: 'var(--surface)' }}>
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

