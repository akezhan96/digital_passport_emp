import { renderDemo } from '../renderDemo'
import React, { useEffect, useState, useCallback, useRef } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import CustomFields from '../components/CustomFields'
import Attachments from '../components/Attachments'
import EmployeeDocuments from '../components/EmployeeDocuments'
import ResumeDialog from '../components/ResumeDialog'
import { personnelText, dateLabel } from '../i18n/personnel'
import CareerTab from '../components/CareerTab'
import EmployeeHistory from '../components/EmployeeHistory'
import RowEditor from '../components/RowEditor'
import CandidateEvaluation from '../components/CandidateEvaluation'
import DossierTabs from '../components/DossierSubsections'
import { CANDIDATE_SCOPE, confirmUnsavedLeave } from '../unsavedChanges'
import { employeeDirectoryText } from '../i18n/employeeDirectory'
import { useFormChanges } from '../useFormChanges'
import { employeeRouteTarget, employeeDirectoryTarget, profileHref } from '../appRoute'
import './EmployeesPage.css'

const TABS = ['general', 'education', 'languages', 'training', 'career',
              'candidate', 'competencies', 'metrics', 'documents', 'history']

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

const EMPTY_FILTERS = { org_unit_id: '', position_id: '', birth_year: '', language_id: '',
  language_min_rank: '', education_country_id: '', profile_status: '', include_subunits: true }
const validYear = (value) => value === '' || (/^\d{4}$/.test(value) && Number(value) >= 1900 && Number(value) <= new Date().getFullYear())

export default function EmployeesPage({ routeKey = location.hash }) {
  const { isAdmin } = useAuth()
  const entryTarget = employeeRouteTarget(routeKey, TABS.filter(key => key !== 'history' || isAdmin))
  const [directoryTarget] = useState(() => employeeDirectoryTarget(location.hash))
  const [resumeOpen, setResumeOpen] = useState(false)
  const { t, pick, lang, text } = useI18n()
  const labels = employeeDirectoryText(lang)
  const ref = useRefData()
  const [list, setList] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState(directoryTarget.search)
  const [query, setQuery] = useState(directoryTarget.search)
  const [filters, setFilters] = useState(() => ({ ...EMPTY_FILTERS, profile_status: directoryTarget.profile_status }))
  const [moreFilters, setMoreFilters] = useState(Boolean(directoryTarget.profile_status))
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [sort, setSort] = useState('name')
  const [listLoading, setListLoading] = useState(true)
  const listRequest = useRef(0)
  const detailRequest = useRef(0)
  const selectedId = entryTarget.employeeId
  const [detail, setDetail] = useState(null)
  const [summary, setSummary] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const tab = entryTarget.tab === 'competencies' && !detail?.assessment_sessions?.length ? 'general' : entryTarget.tab
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [showCreate, setShowCreate] = useState(directoryTarget.create && isAdmin)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => { setPage(0); setQuery(search.trim()) }, 280)
    return () => clearTimeout(timer)
  }, [search])

  const loadList = useCallback(() => {
    const request = ++listRequest.current
    if (!validYear(filters.birth_year)) { setListLoading(false); return }
    const params = { search: query || undefined, limit: pageSize, offset: page * pageSize, sort_by: sort }
    for (const [key, value] of Object.entries(filters)) {
      if (value !== '' && value !== null) params[key] = value
    }
    if (!filters.language_id) delete params.language_min_rank
    if (!filters.org_unit_id) delete params.include_subunits
    setListLoading(true)
    api.employees(params).then((response) => {
      if (request !== listRequest.current) return
      const result = response.data
      const lastPage = Math.max(0, Math.ceil(result.total / pageSize) - 1)
      if (page > lastPage) { setPage(lastPage); return }
      setList(result.data); setTotal(result.total)
    }).catch((e) => {
      if (request === listRequest.current) setError(errorMessage(e))
    }).finally(() => {
      if (request === listRequest.current) setListLoading(false)
    })
  }, [query, page, pageSize, filters, sort])

  useEffect(() => { loadList() }, [loadList])
  useEffect(() => () => { listRequest.current += 1; detailRequest.current += 1 }, [])

  const loadDetail = useCallback((id) => {
    if (!id) return
    const request = ++detailRequest.current
    setDetailLoading(true)
    Promise.all([api.employee(id), api.employeeSummary(id)])
      .then(([d, s]) => {
        if (request === detailRequest.current) { setDetail(d.data); setSummary(s.data) }
      }).catch((e) => {
        if (request === detailRequest.current) setError(errorMessage(e))
      }).finally(() => {
        if (request === detailRequest.current) setDetailLoading(false)
      })
  }, [])

  useEffect(() => {
    detailRequest.current += 1
    setDetail(null); setSummary(null); setResumeOpen(false); setError(null); setNotice(null)
    setDetailLoading(Boolean(selectedId))
    if (selectedId) { setShowCreate(false); loadDetail(selectedId) }
  }, [selectedId, loadDetail])

  const refresh = () => { loadDetail(selectedId); loadList(); setRevision((n) => n + 1) }
  const openEmployee = id => { location.hash = profileHref(routeKey, id) }
  const closeEmployee = () => { location.hash = profileHref(routeKey, null) }
  const setFilter = (key, value) => {
    setPage(0); setError(null)
    setFilters((previous) => ({ ...previous, [key]: value,
      ...(key === 'language_id' && !value ? { language_min_rank: '' } : {}) }))
  }
  const resetFilters = () => {
    setSearch(''); setQuery(''); setFilters(EMPTY_FILTERS); setPage(0); setError(null)
  }
  const verify = async () => {
    setError(null); setNotice(null)
    try { await api.employeeVerify(selectedId); setNotice(t('employee.verified')); refresh() }
    catch (e) { setError(errorMessage(e)) }
  }
  const hasFilters = Boolean(search || Object.entries(filters).some(([key, value]) => key !== 'include_subunits' && value))
  const extraCount = ['birth_year', 'language_id', 'language_min_rank', 'education_country_id', 'profile_status'].filter((key) => filters[key]).length
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const selectedIndex = list.findIndex((employee) => employee.id === selectedId)
  const cefrScale = (ref['language-scales'] || []).find((scale) => scale.code === 'CEFR')
  const levels = (ref['language-levels'] || []).filter((level) => level.scale_id === cefrScale?.id).sort((a, b) => a.rank - b.rank)

  return (
    <div className="employee-directory">
      {selectedId ? (
        <div className="employee-card-navigation">
          <button className="btn btn-ghost btn-sm" onClick={closeEmployee}>← {labels.back}</button>
          <div className="btn-row">
            {selectedIndex >= 0 && <span className="muted">{labels.currentPage}: {selectedIndex + 1} / {list.length}</span>}
            <button className="btn btn-ghost btn-sm" aria-label={labels.previousEmployee}
                    disabled={selectedIndex <= 0 || detailLoading} onClick={() => openEmployee(list[selectedIndex - 1].id)}>←</button>
            <button className="btn btn-ghost btn-sm" aria-label={labels.nextEmployee}
                    disabled={selectedIndex < 0 || selectedIndex >= list.length - 1 || detailLoading}
                    onClick={() => openEmployee(list[selectedIndex + 1].id)}>→</button>
          </div>
        </div>
      ) : (
        <div className="employee-directory-heading">
          <div><h2>{t('employee.title')}</h2><p className="page-hint">{labels.hint}</p></div>
          {isAdmin && <button className="btn" onClick={() => { if (confirmUnsavedLeave(`${CANDIDATE_SCOPE}:create`)) setShowCreate(!showCreate) }}>
            {showCreate ? t('common.cancel') : t('employee.add')}
          </button>}
        </div>
      )}
      {error && <div className="alert alert-bad" role="alert">{error}
        <button className="btn btn-ghost btn-sm" onClick={() => { setError(null); selectedId ? loadDetail(selectedId) : loadList() }}>{labels.retry}</button>
      </div>}
      {notice && <div className="alert alert-ok" role="status">{notice}</div>}
      {!selectedId ? (
        <>
          {isAdmin && showCreate && <div className="employee-directory-create">
            <CreateEmployee ref_={ref} pick={pick} t={t}
              onDone={(id) => { setShowCreate(false); loadList(); openEmployee(id) }} onError={setError} />
          </div>}
          <div className="card employee-directory-filters">
            <div className="employee-directory-filter-main">
              <div className="field"><label htmlFor="employee-search">{labels.searchLabel}</label>
                <input id="employee-search" type="search" maxLength={200} placeholder={labels.search}
                       value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <div className="field"><label htmlFor="employee-unit">{t('employee.orgUnit')}</label>
                <select id="employee-unit" value={filters.org_unit_id} onChange={(e) => setFilter('org_unit_id', e.target.value)}>
                  <option value="">{labels.allUnits}</option>
                  {(ref['org-units'] || []).map((unit) => <option key={unit.id} value={unit.id}>{pick(unit)}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="employee-position">{t('employee.position')}</label>
                <select id="employee-position" value={filters.position_id} onChange={(e) => setFilter('position_id', e.target.value)}>
                  <option value="">{labels.allPositions}</option>
                  {(ref['positions'] || []).map((position) => <option key={position.id} value={position.id}>{pick(position)}</option>)}
                </select>
              </div>
            </div>
            <div className="employee-directory-filter-actions">
              <button className="btn btn-ghost btn-sm" aria-expanded={moreFilters} aria-controls="employee-extra-filters"
                      onClick={() => setMoreFilters(!moreFilters)}>{labels.moreFilters}{extraCount > 0 ? ` · ${extraCount}` : ''} {moreFilters ? '−' : '+'}</button>
              {hasFilters && <button className="btn btn-ghost btn-sm" onClick={resetFilters}>{labels.reset}</button>}
              {filters.org_unit_id && <label className="employee-directory-check"><input type="checkbox" checked={filters.include_subunits}
                onChange={(e) => setFilter('include_subunits', e.target.checked)} />{labels.includeSubunits}</label>}
            </div>
            {moreFilters && <div id="employee-extra-filters" className="employee-directory-filter-extra">
              <div className="field"><label htmlFor="employee-birth-year">{labels.birthYear}</label>
                <input id="employee-birth-year" type="number" min={1900} max={new Date().getFullYear()} placeholder="1985"
                       aria-invalid={!validYear(filters.birth_year)} aria-describedby={!validYear(filters.birth_year) ? 'employee-year-error' : undefined}
                       value={filters.birth_year} onChange={(e) => setFilter('birth_year', e.target.value)} />
                {!validYear(filters.birth_year) && <small id="employee-year-error" style={{ color: 'var(--bad)' }}>{labels.invalidYear}</small>}
              </div>
              <div className="field"><label htmlFor="employee-language">{labels.language}</label>
                <select id="employee-language" value={filters.language_id} onChange={(e) => setFilter('language_id', e.target.value)}>
                  <option value="">{labels.allLanguages}</option>
                  {(ref['languages'] || []).map((language) => <option key={language.id} value={language.id}>{pick(language)}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="employee-language-level">{labels.minimumLevel}</label>
                <select id="employee-language-level" disabled={!filters.language_id} value={filters.language_min_rank}
                        onChange={(e) => setFilter('language_min_rank', e.target.value)}>
                  <option value="">{labels.anyLevel}</option>
                  {levels.map((level) => <option key={level.id} value={level.rank}>{level.code}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="employee-education-country">{labels.educationCountry}</label>
                <select id="employee-education-country" value={filters.education_country_id} onChange={(e) => setFilter('education_country_id', e.target.value)}>
                  <option value="">{labels.allCountries}</option>
                  {(ref['countries'] || []).map((country) => <option key={country.id} value={country.id}>{pick(country)}</option>)}
                </select>
              </div>
              <div className="field"><label htmlFor="employee-profile-status">{labels.status}</label>
                <select id="employee-profile-status" value={filters.profile_status} onChange={(e) => setFilter('profile_status', e.target.value)}>
                  <option value="">{labels.allStatuses}</option>
                  {['draft', 'in_review', 'verified', 'archived'].map((status) => <option key={status} value={status}>{t(`employee.status.${status}`)}</option>)}
                </select>
              </div>
            </div>}
          </div>
          <div className="employee-directory-toolbar">
            <div role="status" aria-live="polite">{labels.found}: <strong>{total}</strong>
              {listLoading && <span className="employee-directory-loading">{labels.loading}</span>}
            </div>
            <div className="employee-directory-controls">
              <label>{labels.sort}<select value={sort} onChange={(e) => { setSort(e.target.value); setPage(0) }}>
                {Object.entries({ name: labels.sortName, personnel_number: labels.sortNumber, org_unit: labels.sortUnit,
                  position: labels.sortPosition, birth_date: labels.sortBirth }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select></label>
              <label>{labels.rows}<select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0) }}>
                {[20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
              </select></label>
            </div>
          </div>
          <div className="card flush employee-directory-table" aria-busy={listLoading}>
            <table>
              <thead><tr><th scope="col">{labels.name}</th><th scope="col">{labels.personalNumber}</th>
                <th scope="col">{t('employee.orgUnit')}</th><th scope="col">{t('employee.position')}</th>
                <th scope="col">{labels.birthYear}</th><th scope="col">{labels.status}</th></tr></thead>
              <tbody>
                {!list.length && <tr><td colSpan={6}><div className="empty">
                  {listLoading ? labels.loading : <>{labels.empty}<div className="muted">{labels.emptyHint}</div></>}
                </div></td></tr>}
                {list.map((employee) => <tr key={employee.id}>
                  <td><button className="employee-directory-profile" disabled={listLoading}
                    aria-label={`${labels.openProfile}: ${employee.full_name}`} onClick={() => openEmployee(employee.id)}>{employee.full_name}</button>
                  </td>
                  <td>{employee.personnel_number || '—'}</td>
                  <td>{employee[`org_unit_name_${lang}`] || employee.org_unit_name_ru || '—'}</td>
                  <td>{employee[`position_name_${lang}`] || employee.position_name_ru || '—'}</td>
                  <td>{employee.birth_year || '—'}</td>
                  <td><span className={`badge ${employee.profile_status === 'verified' ? 'badge-ok' : employee.profile_status === 'archived' ? 'badge-closed' : 'badge-warn'}`}>
                    {t(`employee.status.${employee.profile_status}`)}</span></td>
                </tr>)}
              </tbody>
            </table>
          </div>
          <div className="employee-directory-pager">
            <span>{total ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, total)} / {total}</span>
            <div className="btn-row"><button className="btn btn-ghost btn-sm" disabled={page === 0 || listLoading} onClick={() => setPage(page - 1)}>{labels.previous}</button>
              <span>{labels.page} {page + 1} {labels.of} {pages}</span>
              <button className="btn btn-ghost btn-sm" disabled={page + 1 >= pages || listLoading} onClick={() => setPage(page + 1)}>{labels.next}</button>
            </div>
          </div>
        </>
      ) : detail?.id !== selectedId ? (
        <div className="card"><div className="empty" role="status">{detailLoading ? labels.loading : t('common.select')}</div></div>
      ) : (
        <>
          <div className="card employee-profile-header">
            <div className="employee-profile-heading">
              <div className="employee-profile-identity">
                <h3>{detail.last_name} {detail.first_name} {detail.middle_name || ''}</h3>
                <p>{detail.active_disposal_since ? <span className="badge badge-warn">{personnelText(lang).disposal} · {dateLabel(detail.active_disposal_since)}</span>
                  : [pick(byId(ref['positions'], detail.current_position_id)), pick(byId(ref['org-units'], detail.current_org_unit_id))].filter(Boolean).join(' · ') || '—'}</p>
                <small>{labels.personalNumber}: <strong>{detail.personnel_number || '—'}</strong> · {labels.profileCode}: {detail.anonymous_code}</small>
              </div>
              <span className={`badge ${detail.profile_status === 'verified' ? 'badge-ok' : detail.profile_status === 'archived' ? 'badge-closed' : 'badge-warn'}`}>{t(`employee.status.${detail.profile_status}`)}</span>
            </div>
            <div className="employee-profile-toolbar">
              {summary && <div className="employee-profile-completeness"><span>{labels.filledSections}: <strong>{summary.completeness.percent}%</strong></span>
                <div className="meter"><div className="meter-fill" style={{ width: `${summary.completeness.percent}%` }} /></div>
                <small>{labels.completenessHint}</small>
              </div>}
              <div className="employee-profile-buttons">
                <button className="btn btn-ghost btn-sm" onClick={() => setResumeOpen(true)}>{t('resume.create')}</button>
                {isAdmin && detail.profile_status !== 'verified' && detail.profile_status !== 'archived' && <button className="btn btn-sm" onClick={verify}>{t('employee.verify')}</button>}
                {isAdmin && <ProfileActions detail={detail} t={t} onError={setError} onChanged={refresh}
                  onRemoved={() => { closeEmployee(true); loadList() }} />}
              </div>
            </div>
            {resumeOpen && <ResumeDialog key={detail.id} employee={detail} onClose={() => setResumeOpen(false)} />}
            {summary?.completeness?.warnings?.length > 0 && <div className="alert alert-warn" style={{ marginTop: 14, marginBottom: 0 }}>
              {summary.completeness.warnings.map((warning, index) => <div key={index}>⚠ {text(warning)}</div>)}
            </div>}
          </div>
          <DossierTabs key={detail.id} employeeId={detail.id} isAdmin={isAdmin}
            archivedProfile={detail.profile_status === 'archived'} selectedTab={tab} routeKey={routeKey}
            builtins={TABS.filter(key => (isAdmin || key !== 'history') && (key !== 'competencies' || detail.assessment_sessions?.length > 0))
              .map(key => ({ key, label: key === 'candidate' ? labels.evaluation : t(`employee.tabs.${key}`) }))}>
            <EmployeeTab key={detail.id} tab={tab} detail={detail} summary={summary} ref_={ref}
              evaluationId={entryTarget.evaluationId} t={t} pick={pick} onChanged={refresh} onError={setError}
              readOnly={!isAdmin} revision={revision} />
          </DossierTabs>
        </>
      )}
    </div>
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

  const markSaved = useFormChanges(form, { scope: `${CANDIDATE_SCOPE}:create` })
  const [busy, setBusy] = useState(false)
  const submit = async (ev) => {
    ev.preventDefault()
    if (busy) return
    setBusy(true)
    onError(null)
    const body = Object.fromEntries(
      Object.entries(form).filter(([, v]) => v !== '' && v !== null))
    try {
      const r = await api.employeeCreate(body)
      markSaved(); onDone(r.data.id)
    } catch (e) { onError(errorMessage(e)) } finally { setBusy(false) }
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
        <button className="btn" type="submit" disabled={busy}>{t('common.save')}</button>
      </form>
    </div>
  )
}

/* ======================================================================= */

function EmployeeTab({ tab, detail, summary, ref_, t, pick, onChanged, onError,
                       readOnly = false, revision = 0, evaluationId }) {
  if (tab === 'candidate')
    return <CandidateEvaluation employeeId={detail.id} initialEvaluationId={evaluationId} readOnly={readOnly} onChanged={onChanged} />
  if (tab === 'documents')
    return <EmployeeDocuments employeeId={detail.id} />
  if (tab === 'history')
    return <EmployeeHistory employeeId={detail.id} refreshKey={revision} />
  if (tab === 'general')
    return <GeneralTab detail={detail} ref_={ref_} t={t} pick={pick}
                       onChanged={onChanged}
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

function GeneralTab({ detail, ref_, t, pick, onError, readOnly, onChanged }) {
  const [editing, setEditing] = useState(false)

  const rows = [
    [t('employee.lastName'), detail.last_name],
    [t('employee.firstName'), detail.first_name],
    [t('employee.middleName'), detail.middle_name],
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

  if (editing) {
    return (
      <GeneralEdit detail={detail} ref_={ref_} t={t} pick={pick}
                   onError={onError}
                   onCancel={() => setEditing(false)}
                   onSaved={() => { setEditing(false); onChanged?.() }} />
    )
  }

  return (
    <>
      <div className="card flush">
        {!readOnly && (
          <div style={{ padding: '10px 14px',
                        borderBottom: '1px solid var(--slate-200)',
                        display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost btn-sm" onClick={() => { if (confirmUnsavedLeave(CANDIDATE_SCOPE)) setEditing(true) }}>
              {t('edit.edit')}
            </button>
          </div>
        )}
        <div className="facts">
          {rows.map(([label, value], i) => (
            <React.Fragment key={i}>
              <div>{label}</div>
              <div>{value || '—'}</div>
            </React.Fragment>
          ))}
        </div>
      </div>

      <CustomFields entityType="employee" entityId={detail.id} onError={onError}
                    readOnly={readOnly} />
      <Attachments entityType="employee" entityId={detail.id} onError={onError}
                   readOnly={readOnly} />
    </>
  )
}

/**
 * Correcting the facts on a profile.
 *
 * Every change lands in the audit trail with what it was, what it became and
 * the reason given, so a correction is never indistinguishable from the
 * original entry.
 */
function GeneralEdit({ detail, ref_, t, pick, onSaved, onCancel, onError }) {
  const [form, setForm] = useState({
    last_name: detail.last_name || '',
    first_name: detail.first_name || '',
    middle_name: detail.middle_name || '',
    personnel_number: detail.personnel_number || '',
    birth_date: detail.birth_date || '',
    birth_place: detail.birth_place || '',
    birth_country_id: detail.birth_country_id ?? '',
    nationality_id: detail.nationality_id ?? '',
    hire_date: detail.hire_date || '',
    email: detail.email || '',
    phone: detail.phone || '',
  })
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const scope = `${CANDIDATE_SCOPE}:general`
  const markSaved = useFormChanges({ form, reason }, { scope })
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const submit = async (ev) => {
    ev.preventDefault()
    onError(null)
    setBusy(true)
    try {
      const body = {}
      Object.entries(form).forEach(([key, value]) => {
        if (key.endsWith('_id')) body[key] = value === '' ? null : Number(value)
        else body[key] = value === '' ? null : value
      })
      await api.employeeUpdate(detail.id, body, reason.trim() || undefined)
      markSaved(); onSaved()
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <h3>{t('edit.edit')}</h3>
      <div className="alert alert-info">{t('edit.hint')}</div>
      <form onSubmit={submit}>
        <div className="form-row-3">
          <div className="field">
            <label>{t('employee.lastName')}</label>
            <input value={form.last_name} required onChange={set('last_name')} />
          </div>
          <div className="field">
            <label>{t('employee.firstName')}</label>
            <input value={form.first_name} required onChange={set('first_name')} />
          </div>
          <div className="field">
            <label>{t('employee.middleName')}</label>
            <input value={form.middle_name} onChange={set('middle_name')} />
          </div>
        </div>

        <div className="form-row-3">
          <div className="field">
            <label>{t('employee.personnelNumber')}</label>
            <input value={form.personnel_number} onChange={set('personnel_number')} />
          </div>
          <div className="field">
            <label>{t('employee.birthDate')}</label>
            <input type="date" value={form.birth_date} onChange={set('birth_date')} />
          </div>
          <div className="field">
            <label>{t('employee.hireDate')}</label>
            <input type="date" value={form.hire_date} onChange={set('hire_date')} />
          </div>
        </div>

        <div className="form-row-3">
          <div className="field">
            <label>{t('employee.birthPlace')}</label>
            <input value={form.birth_place} onChange={set('birth_place')} />
          </div>
          <div className="field">
            <label>{t('employee.birthCountry')}</label>
            <select value={form.birth_country_id} onChange={set('birth_country_id')}>
              <option value="">—</option>
              {(ref_['countries'] || []).map((o) => (
                <option key={o.id} value={o.id}>{pick(o)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t('employee.nationality')}</label>
            <select value={form.nationality_id} onChange={set('nationality_id')}>
              <option value="">—</option>
              {(ref_['nationalities'] || []).map((o) => (
                <option key={o.id} value={o.id}>{pick(o)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label>{t('employee.email')}</label>
            <input type="email" value={form.email} onChange={set('email')} />
          </div>
          <div className="field">
            <label>{t('employee.phone')}</label>
            <input value={form.phone} onChange={set('phone')} />
          </div>
        </div>

        <div className="field">
          <label>{t('edit.reason')}</label>
          <input aria-label={t('edit.reason')} value={reason} onChange={(e) => setReason(e.target.value)}
                 placeholder={t('edit.reasonHint')} />
        </div>

        <div className="btn-row">
          <button className="btn" type="submit" disabled={busy}>
            {t('common.save')}
          </button>
          <button className="btn btn-ghost" type="button" onClick={() => { if (confirmUnsavedLeave(scope)) onCancel() }}>
            {t('common.cancel')}
          </button>
        </div>
      </form>
    </div>
  )
}

/**
 * Archiving and deleting a profile.
 *
 * These are different acts. A profile entered by mistake should go entirely.
 * One that has been ranked against a vacancy cannot: the ranking is the record
 * of how a decision was justified, and a short-list pointing at a deleted
 * candidate is worse than no short-list. The API decides which applies, and
 * this panel simply reports what it says.
 */
function ProfileActions({ detail, t, onChanged, onRemoved, onError }) {
  const { lang } = useI18n()
  const labels = employeeDirectoryText(lang)
  const [usage, setUsage] = useState(null)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setOpen(false)
  }, [detail.id])

  useEffect(() => {
    setUsage(null)
    if (!open) return
    let cancelled = false
    api.employeeUsage(detail.id)
      .then((r) => { if (!cancelled) setUsage(r.data) })
      .catch((e) => { if (!cancelled) onError(errorMessage(e)) })
    return () => { cancelled = true }
  }, [open, detail.id])

  const act = async (fn, confirmKey) => {
    if (!window.confirm(t(confirmKey))) return
    onError(null)
    setBusy(true)
    try {
      await fn()
      return true
    } catch (e) {
      onError(errorMessage(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  if (detail.profile_status === 'archived') {
    return (
      <button className="btn btn-ghost btn-sm" disabled={busy}
              onClick={async () => {
                if (await act(() => api.employeeRestore(detail.id),
                              'employee.restoreWarn')) onChanged()
              }}>
        {t('employee.restore')}
      </button>
    )
  }

  if (!open) {
    return (
      <button className="btn btn-ghost btn-sm" aria-expanded="false" onClick={() => setOpen(true)}>
        {labels.more}
      </button>
    )
  }

  const canDelete = usage?.can_delete

  return (
    <div className="employee-profile-more">
      <button className="btn btn-ghost btn-sm" aria-expanded="true" onClick={() => setOpen(false)}>{labels.more}</button>
      <div className="employee-profile-danger-panel">
      <strong>{labels.dangerousActions}</strong>
      <div style={{ fontSize: 12.5, marginBottom: 8 }}>
        {canDelete === false ? (
          <span>
            {t('employee.cannotDelete')}
            <span className="muted">
              {' '}({t('employee.inMatching')}: {usage.matching_results})
            </span>
          </span>
        ) : (
          <span>{t('employee.removeHint')}</span>
        )}
      </div>

      {usage && canDelete && (
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>
          {t('employee.willRemove')}: {t('employee.tabs.education')} {usage.education},
          {' '}{t('employee.tabs.languages')} {usage.languages},
          {' '}{t('employee.tabs.career')} {usage.career},
          {' '}{t('extra.attachments')} {usage.attachments}
          {usage.dossier_entries > 0 && <>, {labels.subsectionEntries} {usage.dossier_entries}</>}
          {usage.personnel_records > 0 && <>, {labels.personnelRecords} {usage.personnel_records}</>}
          {usage.disposal_periods > 0 && <>, {labels.disposalPeriods} {usage.disposal_periods}</>}
        </div>
      )}

      <input aria-label={t('edit.reason')} value={reason} onChange={(e) => setReason(e.target.value)}
             placeholder={t('edit.reasonHint')}
             style={{ marginBottom: 8, fontSize: 12.5 }} />

      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" disabled={busy}
                onClick={async () => {
                  if (await act(() => api.employeeArchive(detail.id,
                                        reason.trim() || undefined),
                                'employee.archiveWarn')) onChanged()
                }}>
          {t('employee.archive')}
        </button>
        {canDelete && (
          <button className="btn btn-danger btn-sm" disabled={busy}
                  onClick={async () => {
                    if (!confirmUnsavedLeave(CANDIDATE_SCOPE)) return
                    if (await act(() => api.employeeDelete(detail.id,
                                          reason.trim() || undefined),
                                  'employee.deleteWarn')) onRemoved()
                  }}>
            {labels.deletePermanently}
          </button>
        )}
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </button>
      </div>
      </div>
    </div>
  )
}

function SectionTable({ columns, rows, onDelete, t, addForm,
                       attachEntity, onError, readOnly = false,
                       editSection, editFields, refData, onChanged }) {
  // Which row has its document panel open, and which is being corrected.
  const [openRow, setOpenRow] = useState(null)
  const [editRow, setEditRow] = useState(null)
  const canEdit = !readOnly && editSection && editFields

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
                      {canEdit && (
                        <button className="btn btn-ghost btn-sm"
                                onClick={() => { if (confirmUnsavedLeave(`${CANDIDATE_SCOPE}:row-${editSection}`)) setEditRow(editRow === r.key ? null : r.key) }}>
                          {t('edit.edit')}
                        </button>
                      )}
                      {!renderDemo && attachEntity && (
                        <button className="btn btn-ghost btn-sm"
                                onClick={() => { if (confirmUnsavedLeave(`${CANDIDATE_SCOPE}:attachment-${attachEntity}`)) setOpenRow(openRow === r.key ? null : r.key) }}>
                          📎 {openRow === r.key ? '▲' : '▼'}
                        </button>
                      )}
                      {!readOnly && (
                        <button className="btn btn-danger btn-sm"
                                onClick={() => { if (confirmUnsavedLeave(`${CANDIDATE_SCOPE}:row-${editSection}:${r.key}`)) onDelete(r.key) }}>
                          {t('common.delete')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {canEdit && editRow === r.key && (
                  <tr>
                    <td colSpan={columns.length + 1} style={{ padding: 8 }}>
                      <RowEditor section={editSection} row={r.source || {}}
                                 fields={editFields} refData={refData || {}}
                                 onError={onError}
                                 onCancel={() => setEditRow(null)}
                                 onSaved={() => { setEditRow(null); onChanged?.() }} />
                    </td>
                  </tr>
                )}
                {!renderDemo && attachEntity && openRow === r.key && (
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
  const markSaved = useFormChanges(f, { enabled: !readOnly, scope: `${CANDIDATE_SCOPE}:add-EducationTab` })

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addEducation(detail.id, {
        ...f,
        start_year: f.start_year ? Number(f.start_year) : null,
        end_year: f.end_year ? Number(f.end_year) : null,
      })
      const empty = { level_id: null, institution: '', country_id: null, field_id: null,
             start_year: '', end_year: '', qualification: '' }
      markSaved(empty); setF(empty)
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="education" onError={onError} readOnly={readOnly}
      columns={[t('employee.education.level'), t('employee.education.institution'),
                t('employee.education.field'), t('employee.education.endYear')]}
      editSection="education" refData={ref_} onChanged={onChanged}
      editFields={[
        { key: 'level_id', kind: 'ref', catalog: 'education-levels',
          label: t('employee.education.level') },
        { key: 'institution', kind: 'text',
          label: t('employee.education.institution') },
        { key: 'field_id', kind: 'ref', catalog: 'education-fields',
          label: t('employee.education.field') },
        { key: 'start_year', kind: 'number',
          label: t('employee.education.startYear') },
        { key: 'end_year', kind: 'number',
          label: t('employee.education.endYear') },
        { key: 'qualification', kind: 'text',
          label: t('employee.education.qualification') },
      ]}
      rows={detail.educations.map((r) => ({
        key: r.id, source: r,
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
  const markSaved = useFormChanges(f, { enabled: !readOnly, scope: `${CANDIDATE_SCOPE}:add-LanguagesTab` })

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
      const empty = { language_id: null, scale_id: null, level_id: null, is_confirmed: true,
             document: '', confirmed_at: '', valid_until: '' }
      markSaved(empty); setF(empty)
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="language" onError={onError} readOnly={readOnly}
      columns={[t('employee.language.language'), t('employee.language.scale'),
                t('employee.language.level'), t('employee.language.confirmed'),
                t('employee.language.validUntil')]}
      editSection="language" refData={ref_} onChanged={onChanged}
      editFields={[
        { key: 'language_id', kind: 'ref', catalog: 'languages',
          label: t('employee.language.language') },
        { key: 'scale_id', kind: 'ref', catalog: 'language-scales',
          label: t('employee.language.scale') },
        { key: 'level_id', kind: 'ref', catalog: 'language-levels',
          label: t('employee.language.level') },
        { key: 'is_confirmed', kind: 'boolean',
          label: t('employee.language.confirmed') },
        { key: 'document', kind: 'text',
          label: t('employee.language.document') },
        { key: 'confirmed_at', kind: 'date',
          label: t('employee.language.confirmedAt') },
        { key: 'valid_until', kind: 'date',
          label: t('employee.language.validUntil') },
      ]}
      rows={detail.languages.map((r) => ({
        key: r.id, source: r,
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
  const markSaved = useFormChanges(f, { enabled: !readOnly, scope: `${CANDIDATE_SCOPE}:add-TrainingTab` })

  const add = async (ev) => {
    ev.preventDefault(); onError(null)
    try {
      await api.addTraining(detail.id, {
        ...f, date_from: f.date_from || null, date_to: f.date_to || null,
      })
      const empty = { name: '', training_type_id: null, job_family_id: null, provider: '',
             date_from: '', date_to: '', result: '' }
      markSaved(empty); setF(empty)
      onChanged()
    } catch (e) { onError(errorMessage(e)) }
  }

  return (
    <SectionTable t={t} attachEntity="training" onError={onError} readOnly={readOnly}
      columns={[t('employee.training.name'), t('employee.training.jobFamily'),
                t('employee.training.provider'), t('employee.training.dateTo')]}
      editSection="training" refData={ref_} onChanged={onChanged}
      editFields={[
        { key: 'name', kind: 'text', label: t('employee.training.name') },
        { key: 'job_family_id', kind: 'ref', catalog: 'job-families',
          label: t('employee.training.jobFamily') },
        { key: 'provider', kind: 'text', label: t('employee.training.provider') },
        { key: 'date_from', kind: 'date', label: t('employee.training.dateFrom') },
        { key: 'date_to', kind: 'date', label: t('employee.training.dateTo') },
        { key: 'result', kind: 'text', label: t('employee.training.result') },
      ]}
      rows={detail.trainings.map((r) => ({
        key: r.id, source: r,
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

function CompetenciesTab({ detail, ref_, t, pick, onChanged, onError, readOnly }) {
  const [history, setHistory] = useState([])
  const [scaleId, setScaleId] = useState(null)
  const [sessionDate, setSessionDate] = useState('')
  const [scores, setScores] = useState({})
  const markSaved = useFormChanges({ scaleId, sessionDate, scores }, { enabled: !readOnly, scope: `${CANDIDATE_SCOPE}:competencies` })

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
      markSaved({ scaleId, sessionDate: '', scores: {} }); setScores({}); setSessionDate('')
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
