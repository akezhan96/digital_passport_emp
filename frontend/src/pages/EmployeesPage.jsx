import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import CustomFields from '../components/CustomFields'
import Attachments from '../components/Attachments'

const TABS = ['general', 'education', 'languages', 'training', 'career', 'competencies', 'metrics']

/** Load every reference list the employee card needs, once. */
function useRefData() {
  const [ref, setRef] = useState({})
  useEffect(() => {
    const names = ['countries', 'nationalities', 'languages', 'language-scales',
      'language-levels', 'education-levels', 'education-fields', 'job-families',
      'org-unit-types', 'org-units', 'positions', 'training-types',
      'assessment-scales', 'competencies']
    Promise.all(names.map((n) => api.refList(n).then((r) => [n, r.data.data])))
      .then((pairs) => setRef(Object.fromEntries(pairs)))
      .catch(() => setRef({}))
  }, [])
  return ref
}

function Select({ label, value, onChange, options, pick, required, empty = '—' }) {
  return (
    <div className="field">
      <label>{label}</label>
      <select value={value ?? ''} required={required}
              onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">{empty}</option>
        {(options || []).map((o) => (
          <option key={o.id} value={o.id}>{pick(o)}</option>
        ))}
      </select>
    </div>
  )
}

export default function EmployeesPage() {
  const { t, pick } = useI18n()
  const { isAdmin } = useAuth()
  const ref = useRefData()

  const [list, setList] = useState([])
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [summary, setSummary] = useState(null)
  const [tab, setTab] = useState('general')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [showCreate, setShowCreate] = useState(false)

  const loadList = useCallback(() => {
    api.employees({ search: search || undefined, limit: 200 })
      .then((r) => setList(r.data.data))
      .catch((e) => setError(errorMessage(e)))
  }, [search])

  useEffect(() => { loadList() }, [loadList])

  const loadDetail = useCallback((id) => {
    if (!id) return
    Promise.all([api.employee(id), api.employeeSummary(id)])
      .then(([d, s]) => { setDetail(d.data); setSummary(s.data) })
      .catch((e) => setError(errorMessage(e)))
  }, [])

  useEffect(() => { loadDetail(selectedId) }, [selectedId, loadDetail])

  const refresh = () => { loadDetail(selectedId); loadList() }

  const verify = async () => {
    setError(null); setNotice(null)
    try {
      await api.employeeVerify(selectedId)
      setNotice(t('employee.verified'))
      refresh()
    } catch (e) { setError(errorMessage(e)) }
  }

  return (
    <>
      <h2>{t('employee.title')}</h2>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="split">
        {/* ---------------- list ---------------- */}
        <div>
          <div className="card">
            <div className="field" style={{ marginBottom: 10 }}>
              <input placeholder={t('common.search')} value={search}
                     onChange={(e) => setSearch(e.target.value)} />
            </div>
            {isAdmin && (
              <button className="btn" style={{ width: '100%' }}
                      onClick={() => setShowCreate(!showCreate)}>
                {showCreate ? t('common.cancel') : t('employee.add')}
              </button>
            )}
          </div>

          {isAdmin && showCreate && (
            <CreateEmployee ref_={ref} pick={pick} t={t}
              onDone={(id) => { setShowCreate(false); loadList(); setSelectedId(id) }}
              onError={setError} />
          )}

          <div className="card flush">
            <div className="list">
              {list.length === 0 && <div className="empty">{t('common.none')}</div>}
              {list.map((emp) => (
                <div key={emp.id}
                     className={`list-row ${selectedId === emp.id ? 'active' : ''}`}
                     onClick={() => { setSelectedId(emp.id); setTab('general') }}>
                  <div>
                    <div className="list-title">{emp.full_name}</div>
                    <div className="list-sub">
                      {emp.position_name_ru || '—'} · {emp.org_unit_name_ru || '—'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <span className={`badge ${emp.profile_status === 'verified'
                      ? 'badge-ok' : 'badge-warn'}`}>
                      {t(`employee.status.${emp.profile_status}`)}
                    </span>
                    <div className="list-sub">{emp.completeness}%</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ---------------- detail ---------------- */}
        <div>
          {!detail ? (
            <div className="card"><div className="empty">{t('common.select')}</div></div>
          ) : (
            <>
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between',
                              alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
                  <div>
                    <h3 style={{ marginBottom: 4 }}>
                      {detail.last_name} {detail.first_name} {detail.middle_name || ''}
                    </h3>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      {t('employee.anonymousCode')}: <strong>{detail.anonymous_code}</strong>
                      {detail.personnel_number && ` · ${detail.personnel_number}`}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`badge ${detail.profile_status === 'verified'
                      ? 'badge-ok' : 'badge-warn'}`}>
                      {t(`employee.status.${detail.profile_status}`)}
                    </span>
                    {summary && (
                      <div style={{ marginTop: 8, minWidth: 150 }}>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {t('employee.completeness')}: {summary.completeness.percent}%
                        </div>
                        <div className="meter" style={{ marginTop: 4 }}>
                          <div className="meter-fill"
                               style={{ width: `${summary.completeness.percent}%` }} />
                        </div>
                      </div>
                    )}
                    {isAdmin && detail.profile_status !== 'verified' && (
                      <button className="btn btn-sm" style={{ marginTop: 8 }}
                              onClick={verify}>{t('employee.verify')}</button>
                    )}
                  </div>
                </div>

                {summary?.completeness?.warnings?.length > 0 && (
                  <div className="alert alert-warn" style={{ marginTop: 14, marginBottom: 0 }}>
                    {summary.completeness.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
                  </div>
                )}
              </div>

              <div className="tabs">
                {TABS.map((key) => (
                  <button key={key} className={`tab ${tab === key ? 'active' : ''}`}
                          onClick={() => setTab(key)}>
                    {t(`employee.tabs.${key}`)}
                  </button>
                ))}
              </div>

              <EmployeeTab tab={tab} detail={detail} summary={summary} ref_={ref}
                           t={t} pick={pick} onChanged={refresh} onError={setError}
                           readOnly={!isAdmin} />
            </>
          )}
        </div>
      </div>
    </>
  )
}

/* ======================================================================= */

function CreateEmployee({ ref_, pick, t, onDone, onError }) {
  const [form, setForm] = useState({
    last_name: '', first_name: '', middle_name: '', personnel_number: '',
    birth_date: '', birth_place: '', birth_country_id: null, nationality_id: null,
    email: '', phone: '', hire_date: '',
    current_position_id: null, current_org_unit_id: null,
  })

  const submit = async (ev) => {
    ev.preventDefault()
    onError(null)
    const body = Object.fromEntries(
      Object.entries(form).filter(([, v]) => v !== '' && v !== null))
    try {
      const r = await api.employeeCreate(body)
      onDone(r.data.id)
    } catch (e) { onError(errorMessage(e)) }
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="card">
      <h3>{t('employee.add')}</h3>
      <form onSubmit={submit}>
        <div className="field">
          <label>{t('employee.lastName')}</label>
          <input value={form.last_name} onChange={set('last_name')} required />
        </div>
        <div className="field">
          <label>{t('employee.firstName')}</label>
          <input value={form.first_name} onChange={set('first_name')} required />
        </div>
        <div className="field">
          <label>{t('employee.middleName')}</label>
          <input value={form.middle_name} onChange={set('middle_name')} />
        </div>
        <div className="form-row">
          <div className="field">
            <label>{t('employee.personnelNumber')}</label>
            <input value={form.personnel_number} onChange={set('personnel_number')} />
          </div>
          <div className="field">
            <label>{t('employee.birthDate')}</label>
            <input type="date" value={form.birth_date} onChange={set('birth_date')} />
          </div>
        </div>
        <div className="field">
          <label>{t('employee.birthPlace')}</label>
          <input value={form.birth_place} onChange={set('birth_place')} />
        </div>
        <div className="form-row">
          <Select label={t('employee.birthCountry')} value={form.birth_country_id}
                  options={ref_['countries']} pick={pick}
                  onChange={(v) => setForm({ ...form, birth_country_id: v })} />
          <Select label={t('employee.nationality')} value={form.nationality_id}
                  options={ref_['nationalities']} pick={pick}
                  onChange={(v) => setForm({ ...form, nationality_id: v })} />
        </div>
        <div className="form-row">
          <div className="field">
            <label>{t('employee.hireDate')}</label>
            <input type="date" value={form.hire_date} onChange={set('hire_date')} />
          </div>
          <div className="field">
            <label>{t('employee.email')}</label>
            <input value={form.email} onChange={set('email')} />
          </div>
        </div>
        <div className="form-row">
          <Select label={t('employee.orgUnit')} value={form.current_org_unit_id}
                  options={ref_['org-units']} pick={pick}
                  onChange={(v) => setForm({ ...form, current_org_unit_id: v })} />
          <Select label={t('employee.position')} value={form.current_position_id}
                  options={ref_['positions']} pick={pick}
                  onChange={(v) => setForm({ ...form, current_position_id: v })} />
        </div>
        <button className="btn" type="submit">{t('common.save')}</button>
      </form>
    </div>
  )
}

/* ======================================================================= */

function EmployeeTab({ tab, detail, summary, ref_, t, pick, onChanged, onError,
                       readOnly = false }) {
  if (tab === 'general')
    return <GeneralTab detail={detail} ref_={ref_} t={t} pick={pick}
                       onError={onError} readOnly={readOnly} />
  if (tab === 'education')
    return <EducationTab detail={detail} ref_={ref_} t={t} pick={pick} readOnly={readOnly}
                         onChanged={onChanged} onError={onError} />
  if (tab === 'languages')
    return <LanguagesTab detail={detail} ref_={ref_} t={t} pick={pick} readOnly={readOnly}
                         onChanged={onChanged} onError={onError} />
  if (tab === 'training')
    return <TrainingTab detail={detail} ref_={ref_} t={t} pick={pick} readOnly={readOnly}
                        onChanged={onChanged} onError={onError} />
  if (tab === 'career')
    return <CareerTab detail={detail} ref_={ref_} t={t} pick={pick} readOnly={readOnly}
                      onChanged={onChanged} onError={onError} />
  if (tab === 'competencies')
    return <CompetenciesTab detail={detail} ref_={ref_} t={t} pick={pick} readOnly={readOnly}
                            onChanged={onChanged} onError={onError} />
  return <MetricsTab summary={summary} t={t} />
}

function byId(list, id) { return (list || []).find((x) => x.id === id) }

function GeneralTab({ detail, ref_, t, pick, onError, readOnly }) {
  const rows = [
    [t('employee.personnelNumber'), detail.personnel_number],
    [t('employee.birthDate'), detail.birth_date],
    [t('employee.birthPlace'), detail.birth_place],
    [t('employee.birthCountry'), pick(byId(ref_['countries'], detail.birth_country_id))],
    [t('employee.nationality'), pick(byId(ref_['nationalities'], detail.nationality_id))],
    [t('employee.hireDate'), detail.hire_date],
    [t('employee.orgUnit'), pick(byId(ref_['org-units'], detail.current_org_unit_id))],
    [t('employee.position'), pick(byId(ref_['positions'], detail.current_position_id))],
    [t('employee.email'), detail.email],
    [t('employee.phone'), detail.phone],
  ]
  return (
    <>
      <div className="card flush">
        <table><tbody>
          {rows.map(([label, value], i) => (
            <tr key={i}>
              <td className="muted" style={{ width: 220 }}>{label}</td>
              <td>{value || '—'}</td>
            </tr>
          ))}
        </tbody></table>
      </div>

      <CustomFields entityType="employee" entityId={detail.id} onError={onError}
                    readOnly={readOnly} />
      <Attachments entityType="employee" entityId={detail.id} onError={onError}
                   readOnly={readOnly} />
    </>
  )
}

function SectionTable({ columns, rows, onDelete, t, addForm,
                       attachEntity, onError, readOnly = false }) {
  // Which row has its document panel open.
  const [openRow, setOpenRow] = useState(null)

  return (
    <>
      <div className="card flush">
        <table>
          <thead><tr>
            {columns.map((c) => <th key={c}>{c}</th>)}
            <th style={{ width: 170 }} />
          </tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={columns.length + 1} className="empty">
                {t('common.none')}
              </td></tr>
            )}
            {rows.map((r) => (
              <React.Fragment key={r.key}>
                <tr>
                  {r.cells.map((cell, i) => <td key={i}>{cell}</td>)}
                  <td>
                    <div className="btn-row">
                      {attachEntity && (
                        <button className="btn btn-ghost btn-sm"
                                onClick={() => setOpenRow(
                                  openRow === r.key ? null : r.key)}>
                          📎 {openRow === r.key ? '▲' : '▼'}
                        </button>
                      )}
                      {!readOnly && (
                        <button className="btn btn-danger btn-sm"
                                onClick={() => onDelete(r.key)}>
                          {t('common.delete')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {attachEntity && openRow === r.key && (
                  <tr>
                    <td colSpan={columns.length + 1}
                        style={{ background: 'var(--slate-50)' }}>
                      <Attachments entityType={attachEntity} entityId={r.key}
                                   compact onError={onError} readOnly={readOnly} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {!readOnly && addForm}
    </>
  )
}

function EducationTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [f, setF] = useState({ level_id: null, institution: '', country_id: null,
    field_id: null, start_year: '', end_year: '', qualification: '' })

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addEducation(detail.id, {
        ...f,
        start_year: f.start_year ? Number(f.start_year) : null,
        end_year: f.end_year ? Number(f.end_year) : null,
      })
      setF({ level_id: null, institution: '', country_id: null, field_id: null,
             start_year: '', end_year: '', qualification: '' })
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="education" onError={onError} readOnly={readOnly}
      columns={[t('employee.education.level'), t('employee.education.institution'),
                t('employee.education.field'), t('employee.education.endYear')]}
      rows={detail.educations.map((r) => ({
        key: r.id,
        cells: [pick(byId(ref_['education-levels'], r.level_id)), r.institution,
                pick(byId(ref_['education-fields'], r.field_id)) || '—', r.end_year || '—'],
      }))}
      onDelete={async (id) => { await api.delEducation(id); onChanged() }}
      addForm={
        <div className="card">
          <h3>{t('common.add')}</h3>
          <form onSubmit={add}>
            <div className="form-row">
              <Select label={t('employee.education.level')} value={f.level_id} required
                      options={ref_['education-levels']} pick={pick}
                      onChange={(v) => setF({ ...f, level_id: v })} />
              <Select label={t('employee.education.field')} value={f.field_id}
                      options={ref_['education-fields']} pick={pick}
                      onChange={(v) => setF({ ...f, field_id: v })} />
            </div>
            <div className="field">
              <label>{t('employee.education.institution')}</label>
              <input value={f.institution} required
                     onChange={(e) => setF({ ...f, institution: e.target.value })} />
            </div>
            <div className="form-row-3">
              <Select label={t('common.name')} value={f.country_id}
                      options={ref_['countries']} pick={pick}
                      onChange={(v) => setF({ ...f, country_id: v })} />
              <div className="field">
                <label>{t('employee.education.startYear')}</label>
                <input type="number" value={f.start_year}
                       onChange={(e) => setF({ ...f, start_year: e.target.value })} />
              </div>
              <div className="field">
                <label>{t('employee.education.endYear')}</label>
                <input type="number" value={f.end_year}
                       onChange={(e) => setF({ ...f, end_year: e.target.value })} />
              </div>
            </div>
            <button className="btn" type="submit">{t('common.save')}</button>
          </form>
        </div>
      } />
  )
}

function LanguagesTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [f, setF] = useState({ language_id: null, scale_id: null, level_id: null,
    is_confirmed: true, document: '', confirmed_at: '', valid_until: '' })

  // Only levels belonging to the chosen scale -- this is what makes an
  // impossible level (B3 in CEFR) unselectable in the first place.
  const levels = (ref_['language-levels'] || [])
    .filter((l) => !f.scale_id || l.scale_id === f.scale_id)

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addLanguage(detail.id, {
        ...f,
        confirmed_at: f.confirmed_at || null,
        valid_until: f.valid_until || null,
      })
      setF({ language_id: null, scale_id: null, level_id: null, is_confirmed: true,
             document: '', confirmed_at: '', valid_until: '' })
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="language" onError={onError} readOnly={readOnly}
      columns={[t('employee.language.language'), t('employee.language.scale'),
                t('employee.language.level'), t('employee.language.confirmed'),
                t('employee.language.validUntil')]}
      rows={detail.languages.map((r) => ({
        key: r.id,
        cells: [
          pick(byId(ref_['languages'], r.language_id)),
          pick(byId(ref_['language-scales'], r.scale_id)),
          <strong>{byId(ref_['language-levels'], r.level_id)?.code}</strong>,
          r.is_confirmed
            ? <span className="badge badge-ok">{t('common.yes')}</span>
            : <span className="badge badge-warn">{t('common.no')}</span>,
          r.valid_until || '—',
        ],
      }))}
      onDelete={async (id) => { await api.delLanguage(id); onChanged() }}
      addForm={
        <div className="card">
          <h3>{t('common.add')}</h3>
          <form onSubmit={add}>
            <div className="form-row-3">
              <Select label={t('employee.language.language')} value={f.language_id} required
                      options={ref_['languages']} pick={pick}
                      onChange={(v) => setF({ ...f, language_id: v })} />
              <Select label={t('employee.language.scale')} value={f.scale_id} required
                      options={ref_['language-scales']} pick={pick}
                      onChange={(v) => setF({ ...f, scale_id: v, level_id: null })} />
              <div className="field">
                <label>{t('employee.language.level')}</label>
                <select value={f.level_id ?? ''} required
                        onChange={(e) => setF({ ...f,
                          level_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {levels.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row-3">
              <div className="field">
                <label>{t('employee.language.document')}</label>
                <input value={f.document}
                       onChange={(e) => setF({ ...f, document: e.target.value })} />
              </div>
              <div className="field">
                <label>{t('employee.language.confirmedAt')}</label>
                <input type="date" value={f.confirmed_at}
                       onChange={(e) => setF({ ...f, confirmed_at: e.target.value })} />
              </div>
              <div className="field">
                <label>{t('employee.language.validUntil')}</label>
                <input type="date" value={f.valid_until}
                       onChange={(e) => setF({ ...f, valid_until: e.target.value })} />
              </div>
            </div>
            <button className="btn" type="submit">{t('common.save')}</button>
          </form>
        </div>
      } />
  )
}

function TrainingTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [f, setF] = useState({ name: '', training_type_id: null, job_family_id: null,
    provider: '', date_from: '', date_to: '', result: '' })

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addTraining(detail.id, {
        ...f, date_from: f.date_from || null, date_to: f.date_to || null,
      })
      setF({ name: '', training_type_id: null, job_family_id: null, provider: '',
             date_from: '', date_to: '', result: '' })
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="training" onError={onError} readOnly={readOnly}
      columns={[t('employee.training.name'), t('employee.training.jobFamily'),
                t('employee.training.provider'), t('employee.training.dateTo')]}
      rows={detail.trainings.map((r) => ({
        key: r.id,
        cells: [r.name, pick(byId(ref_['job-families'], r.job_family_id)) || '—',
                r.provider || '—', r.date_to || '—'],
      }))}
      onDelete={async (id) => { await api.delTraining(id); onChanged() }}
      addForm={
        <div className="card">
          <h3>{t('common.add')}</h3>
          <form onSubmit={add}>
            <div className="field">
              <label>{t('employee.training.name')}</label>
              <input value={f.name} required
                     onChange={(e) => setF({ ...f, name: e.target.value })} />
            </div>
            <div className="form-row">
              <Select label={t('employee.training.type')} value={f.training_type_id}
                      options={ref_['training-types']} pick={pick}
                      onChange={(v) => setF({ ...f, training_type_id: v })} />
              <Select label={t('employee.training.jobFamily')} value={f.job_family_id}
                      options={ref_['job-families']} pick={pick}
                      onChange={(v) => setF({ ...f, job_family_id: v })} />
            </div>
            <div className="form-row-3">
              <div className="field">
                <label>{t('employee.training.provider')}</label>
                <input value={f.provider}
                       onChange={(e) => setF({ ...f, provider: e.target.value })} />
              </div>
              <div className="field">
                <label>{t('employee.training.dateFrom')}</label>
                <input type="date" value={f.date_from}
                       onChange={(e) => setF({ ...f, date_from: e.target.value })} />
              </div>
              <div className="field">
                <label>{t('employee.training.dateTo')}</label>
                <input type="date" value={f.date_to}
                       onChange={(e) => setF({ ...f, date_to: e.target.value })} />
              </div>
            </div>
            <button className="btn" type="submit">{t('common.save')}</button>
          </form>
        </div>
      } />
  )
}

function CareerTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [f, setF] = useState({ is_internal: true, org_unit_id: null, position_id: null,
    external_employer: '', external_position_title: '', job_family_id: null,
    org_unit_type_id: null, country_id: null, date_from: '', date_to: '' })

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addCareer(detail.id, { ...f, date_to: f.date_to || null })
      setF({ is_internal: true, org_unit_id: null, position_id: null,
             external_employer: '', external_position_title: '', job_family_id: null,
             org_unit_type_id: null, country_id: null, date_from: '', date_to: '' })
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <>
      <div className="alert alert-info">{t('employee.career.hint')}</div>
      <SectionTable t={t} attachEntity="work_experience" onError={onError} readOnly={readOnly}
        columns={[t('employee.career.orgUnit'), t('employee.career.position'),
                  t('employee.career.jobFamily'), t('employee.career.unitType'),
                  t('employee.career.dateFrom'), t('employee.career.dateTo')]}
        rows={detail.work_experience.map((r) => ({
          key: r.id,
          cells: [
            r.is_internal
              ? pick(byId(ref_['org-units'], r.org_unit_id))
              : (r.external_employer || '—'),
            r.is_internal
              ? pick(byId(ref_['positions'], r.position_id))
              : (r.external_position_title || '—'),
            <span className="badge badge-mute">
              {pick(byId(ref_['job-families'], r.job_family_id))}
            </span>,
            pick(byId(ref_['org-unit-types'], r.org_unit_type_id)),
            r.date_from,
            r.date_to || <em className="muted">{t('employee.career.present')}</em>,
          ],
        }))}
        onDelete={async (id) => { await api.delCareer(id); onChanged() }}
        addForm={
          <div className="card">
            <h3>{t('common.add')}</h3>
            <form onSubmit={add}>
              <div className="form-row">
                <Select label={t('employee.career.orgUnit')} value={f.org_unit_id}
                        options={ref_['org-units']} pick={pick}
                        onChange={(v) => setF({ ...f, org_unit_id: v })} />
                <Select label={t('employee.career.position')} value={f.position_id}
                        options={ref_['positions']} pick={pick}
                        onChange={(v) => setF({ ...f, position_id: v })} />
              </div>
              <div className="form-row-3">
                <Select label={t('employee.career.jobFamily')} value={f.job_family_id}
                        required options={ref_['job-families']} pick={pick}
                        onChange={(v) => setF({ ...f, job_family_id: v })} />
                <Select label={t('employee.career.unitType')} value={f.org_unit_type_id}
                        required options={ref_['org-unit-types']} pick={pick}
                        onChange={(v) => setF({ ...f, org_unit_type_id: v })} />
                <Select label={t('employee.career.country')} value={f.country_id}
                        options={ref_['countries']} pick={pick}
                        onChange={(v) => setF({ ...f, country_id: v })} />
              </div>
              <div className="form-row">
                <div className="field">
                  <label>{t('employee.career.dateFrom')}</label>
                  <input type="date" value={f.date_from} required
                         onChange={(e) => setF({ ...f, date_from: e.target.value })} />
                </div>
                <div className="field">
                  <label>{t('employee.career.dateTo')}</label>
                  <input type="date" value={f.date_to}
                         onChange={(e) => setF({ ...f, date_to: e.target.value })} />
                </div>
              </div>
              <button className="btn" type="submit">{t('common.save')}</button>
            </form>
          </div>
        } />
    </>
  )
}

function CompetenciesTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [history, setHistory] = useState([])
  const [scaleId, setScaleId] = useState(null)
  const [sessionDate, setSessionDate] = useState('')
  const [scores, setScores] = useState({})

  useEffect(() => {
    api.competencyHistory(detail.id).then((r) => setHistory(r.data.data)).catch(() => {})
  }, [detail.id])

  const competencies = (ref_['competencies'] || [])

  const save = async (ev) => {
    ev.preventDefault(); onError(null)
    const list = Object.entries(scores)
      .filter(([, v]) => v !== '' && v !== null)
      .map(([id, v]) => ({ competency_id: Number(id), score: Number(v) }))
    if (!list.length) return
    try {
      await api.addAssessment(detail.id, {
        session_type: 'professional', scale_id: scaleId,
        session_date: sessionDate, scores: list,
      })
      setScores({}); setSessionDate('')
      const r = await api.competencyHistory(detail.id)
      setHistory(r.data.data)
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <>
      <div className="card flush">
        <table>
          <thead><tr>
            <th>{t('employee.tabs.competencies')}</th>
            <th>{t('common.name')}</th>
          </tr></thead>
          <tbody>
            {history.length === 0 && (
              <tr><td colSpan={2} className="empty">{t('common.none')}</td></tr>
            )}
            {history.map((h) => (
              <tr key={h.competency_code}>
                <td><strong>{pick(h)}</strong></td>
                <td>
                  {h.points.map((p, i) => (
                    <span key={i} className="badge badge-mute" style={{ marginRight: 6 }}>
                      {p.date.slice(0, 4)}: {p.score}
                      {p.scale_max ? ` / ${p.scale_max}` : ''}
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!readOnly && (
      <div className="card">
        <h3>{t('common.add')}</h3>
        <form onSubmit={save}>
          <div className="form-row">
            <Select label={t('employee.language.scale')} value={scaleId} required
                    options={ref_['assessment-scales']} pick={pick}
                    onChange={setScaleId} />
            <div className="field">
              <label>{t('audit.date')}</label>
              <input type="date" value={sessionDate} required
                     onChange={(e) => setSessionDate(e.target.value)} />
            </div>
          </div>
          <div className="form-row-3">
            {competencies.map((c) => (
              <div className="field" key={c.id}>
                <label>{pick(c)}</label>
                <input type="number" step="0.1" value={scores[c.id] ?? ''}
                       onChange={(e) => setScores({ ...scores, [c.id]: e.target.value })} />
              </div>
            ))}
          </div>
          <button className="btn" type="submit">{t('common.save')}</button>
        </form>
      </div>
      )}
    </>
  )
}

function MetricsTab({ summary, t }) {
  if (!summary) return <div className="spinner" />
  const entries = Object.entries(summary.metrics)
    .filter(([k]) => !k.startsWith('competency'))
    .sort()
  return (
    <>
      <div className="alert alert-info">{t('employee.metricsHint')}</div>
      <div className="card flush">
        <table>
          <thead><tr><th>{t('common.name')}</th><th className="num">{t('common.years')}</th></tr></thead>
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td className="num"><strong>{Number(v).toFixed(1)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
