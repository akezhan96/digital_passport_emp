import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import StaffingTable from '../components/StaffingTable'
import StaffingOverview from '../components/StaffingOverview'
import { confirmUnsavedLeave } from '../unsavedChanges'
import { appointmentScope } from '../components/AppointmentForm'
import AppointmentPanel from '../components/AppointmentPanel'
import WorklistPager, { useDebounced } from '../components/WorklistPager'
import { worklistText } from '../i18n/worklists'
import './worklists.css'

/**
 * Two views of the workforce: the unit tree with rolled-up headcount, and the
 * standing segments -- who has no posting, who is abroad, who has come back,
 * who is waiting to go.
 *
 * Administrators edit the structure here rather than hunting for it in the
 * catalogues: rename a unit, add a sub-unit, re-parent or remove one, all in
 * the place where the hierarchy is visible.
 */
export default function StructurePage() {
  const { t } = useI18n()
  const [tab, setTab] = useState('tree')
  const [error, setError] = useState(null)
  // Set when the staffing overview asks to open a particular unit, so the
  // tree can select it instead of making the user find it again.
  const [jumpTo, setJumpTo] = useState(null)

  const openUnit = (unitId) => {
    setJumpTo(unitId)
    setTab('tree')
  }

  return (
    <>
      <h2>{t('structure.title')}</h2>
      <p className="page-hint">{t('structure.hint')}</p>

      {error && <div className="alert alert-bad">{error}</div>}

      <div className="tabs">
        <button className={`tab ${tab === 'tree' ? 'active' : ''}`}
                onClick={() => setTab('tree')}>{t('structure.treeTab')}</button>
        <button className={`tab ${tab === 'staffing' ? 'active' : ''}`}
                onClick={() => setTab('staffing')}>{t('staffing.tab')}</button>
        <button className={`tab ${tab === 'segments' ? 'active' : ''}`}
                onClick={() => setTab('segments')}>
          {t('structure.segmentsTab')}
        </button>
      </div>

      {tab === 'tree' && (
        <OrgTree onError={setError} jumpTo={jumpTo}
                 onJumped={() => setJumpTo(null)} />
      )}
      {tab === 'staffing' && (
        <StaffingOverview onError={setError} onOpenUnit={openUnit} />
      )}
      {tab === 'segments' && <Segments onError={setError} />}
    </>
  )
}

/* ------------------------------------------------------------------- tree */

function OrgTree({ onError, jumpTo, onJumped }) {
  const { t, pick } = useI18n()
  const { isAdmin } = useAuth()
  const [tree, setTree] = useState(null)
  const [open, setOpen] = useState({})
  const [selected, setSelected] = useState(null)
  const [mode, setMode] = useState(null)        // 'edit' | 'add' | null
  const [refs, setRefs] = useState({})
  const [notice, setNotice] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  const load = useCallback((keepSelection) => {
    api.orgTree(false)
      .then((r) => {
        setTree(r.data)
        setOpen((prev) => {
          if (Object.keys(prev).length) return prev
          const initial = {}
          // Start with a compact hierarchy; search opens only the matching paths.
          return initial
        })
        if (keepSelection) {
          const flat = []
          const walk = (nodes) => nodes.forEach((n) => {
            flat.push(n); walk(n.children || [])
          })
          walk(r.data.roots || [])
          setSelected((s) => (s ? flat.find((n) => n.id === s.id) || null : null))
        }
      })
      .catch((e) => onError(errorMessage(e)))
  }, [onError])

  useEffect(() => { load(false) }, [load])

  // The staffing overview can ask for a specific unit; open its ancestors so
  // the row is actually visible, then select it.
  useEffect(() => {
    if (!jumpTo || !tree) return
    const parents = {}
    const index = {}
    const walk = (nodes, parent) => nodes.forEach((n) => {
      index[n.id] = n
      parents[n.id] = parent
      walk(n.children || [], n.id)
    })
    walk(tree.roots, null)

    const target = index[jumpTo]
    if (target) {
      setSearchQuery('')
      const expand = {}
      for (let id = parents[jumpTo]; id != null; id = parents[id]) {
        expand[id] = true
      }
      setOpen((prev) => ({ ...prev, ...expand }))
      setSelected(target)
      setMode(null)
    }
    onJumped?.()
  }, [jumpTo, tree, onJumped])

  useEffect(() => {
    if (!isAdmin) return
    Promise.all(['org-unit-types', 'countries', 'positions']
      .map((c) => api.refList(c).then((r) => [c, r.data.data]).catch(() => [c, []])))
      .then((pairs) => setRefs(Object.fromEntries(pairs)))
  }, [isAdmin])

  const collectIds = useCallback((nodes, acc = {}) => {
    nodes.forEach((n) => { acc[n.id] = true; collectIds(n.children || [], acc) })
    return acc
  }, [])

  const search = useMemo(() => {
    const normalize = (value) => String(value || '').normalize('NFKC').toLowerCase().replace(/ё/g, 'е')
    const words = normalize(searchQuery).trim().split(/\s+/).filter(Boolean)
    const matches = new Set()
    const visible = new Set()
    if (words.length) {
      const visit = (node, parentMatched = false) => {
        const text = normalize([node.name_ru, node.name_kk, node.code,
          node.country, node.country_kk, node.region].filter(Boolean).join(' '))
        const matched = words.every((word) => text.includes(word))
        if (matched) matches.add(node.id)
        // Keep original nodes for selection/editing; filter only their visibility.
        const childrenVisible = (node.children || [])
          .map((child) => visit(child, parentMatched || matched)).some(Boolean)
        if (matched || parentMatched || childrenVisible) {
          visible.add(node.id)
          return true
        }
        return false
      }
      ;(tree?.roots || []).forEach((node) => visit(node))
    }
    return { active: words.length > 0, matches, visible }
  }, [tree, searchQuery])

  if (!tree) return <div className="spinner" />

  const flat = []
  const walkAll = (nodes) => nodes.forEach((n) => {
    flat.push(n); walkAll(n.children || [])
  })
  walkAll(tree.roots)

  const afterChange = (message) => {
    setMode(null)
    setNotice(message)
    setTimeout(() => setNotice(null), 3000)
    load(true)
  }

  const renderNode = (node, depth = 0) => {
    if (search.active && !search.visible.has(node.id)) return null
    const hasChildren = (node.children || []).length > 0
    const isOpen = search.active || open[node.id]
    return (
      <React.Fragment key={node.id}>
        <tr className={search.active && search.matches.has(node.id) ? 'structure-search-match' : undefined}
            style={{ background: selected?.id === node.id
          ? 'var(--accent-soft)' : undefined }}>
          <td style={{ paddingLeft: 12 + depth * 22 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {hasChildren ? (
                <button className="btn btn-ghost btn-sm"
                        disabled={search.active}
                        aria-expanded={!!isOpen}
                        aria-label={`${t(isOpen ? 'structure.collapse' : 'structure.expand')}: ${pick(node)}`}
                        style={{ padding: '1px 7px', lineHeight: 1.4 }}
                        onClick={() => setOpen({ ...open, [node.id]: !isOpen })}>
                  {isOpen ? '▾' : '▸'}
                </button>
              ) : <span style={{ display: 'inline-block', width: 26 }} />}
              <button className="btn btn-ghost btn-sm org-unit-name"
                      style={{ border: 0, background: 'transparent',
                               padding: 0, fontWeight: 600 }}
                      onClick={() => { setSelected(node); setMode(null) }}>
                {pick(node)}
              </button>
            </div>
          </td>
          <td className="num"><strong>{node.total_count}</strong></td>
          <td className="num">
            {node.established_total > 0 ? (
              <>
                <strong>{node.established}</strong>
                {node.established_total !== node.established && (
                  <span className="muted" style={{ fontSize: 11 }}>
                    {' / '}{node.established_total}
                  </span>
                )}
              </>
            ) : <span className="muted">—</span>}
          </td>
          <td className="num">
            {node.vacant > 0
              ? <span className="badge badge-ok">{node.vacant}</span>
              : <span className="muted">{node.established > 0 ? 0 : '—'}</span>}
            {node.over_established > 0 && (
              <span className="badge badge-warn" style={{ marginLeft: 4 }}>
                +{node.over_established}
              </span>
            )}
          </td>
        </tr>
        {isOpen && (node.children || []).map((c) => renderNode(c, depth + 1))}
      </React.Fragment>
    )
  }

  return (
    <>
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="split structure-layout">
        <div className="card flush">
          <div style={{ padding: '10px 14px',
                        borderBottom: '1px solid var(--slate-200)',
                        display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: 13 }}>
              {t('structure.treeTab')}
              <span className="muted"> · {tree.total_employees}</span>
              {tree.establishment && tree.establishment.established > 0 && (
                <span className="muted" style={{ fontWeight: 400 }}>
                  {' · '}{t('staffing.established')}:{' '}
                  {tree.establishment.established}
                  {' · '}{t('staffing.vacant')}: {tree.establishment.vacant}
                </span>
              )}
            </strong>
            <div className="btn-row">
              {isAdmin && (
                <button className="btn btn-sm"
                        onClick={() => { setMode('add'); setNotice(null) }}>
                  + {t('structure.addUnit')}
                </button>
              )}
              <button className="btn btn-ghost btn-sm"
                      disabled={search.active}
                      onClick={() => setOpen(collectIds(tree.roots))}>
                {t('structure.expand')}
              </button>
              <button className="btn btn-ghost btn-sm" disabled={search.active} onClick={() => setOpen({})}>
                {t('structure.collapse')}
              </button>
            </div>
          </div>

          <div className="structure-search">
            <label htmlFor="structure-search">{t('structure.searchLabel')}</label>
            <div className="structure-search-controls">
              <input id="structure-search" type="search" value={searchQuery}
                     placeholder={t('structure.searchPlaceholder')}
                     aria-describedby="structure-search-status"
                     autoComplete="off"
                     onChange={(event) => setSearchQuery(event.target.value)}
                     onKeyDown={(event) => {
                       if (event.key === 'Escape') setSearchQuery('')
                     }} />
              {searchQuery && (
                <button className="btn btn-ghost btn-sm" onClick={() => setSearchQuery('')}>
                  {t('structure.clearSearch')}
                </button>
              )}
            </div>
            <div id="structure-search-status" className="muted" role="status" aria-live="polite">
              {search.active
                ? t('structure.searchResults', { count: search.matches.size })
                : t('structure.searchHint')}
            </div>
            {search.active && selected && !search.visible.has(selected.id) && (
              <div className="muted">{t('structure.searchSelection', { name: pick(selected) })}</div>
            )}
          </div>

          <div className="structure-tree-scroll">
            <table>
              <thead><tr>
                <th className="col-grow">{t('employee.orgUnit')}</th>
                <th className="num">{t('structure.total')}</th>
                <th className="num" title={t('staffing.established')}>
                  {t('staffing.headcount')}
                </th>
                <th className="num" title={t('staffing.vacant')}>
                  {t('staffing.vacant')}
                </th>
              </tr></thead>
              <tbody>
                {search.active && search.matches.size === 0 ? (
                  <tr><td colSpan={4}><div className="empty">{t('structure.searchEmpty')}</div></td></tr>
                ) : tree.roots.map((n) => renderNode(n))}
              </tbody>
            </table>
          </div>

          {tree.unplaced.count > 0 && (
            <div style={{ padding: '10px 14px',
                          borderTop: '1px solid var(--slate-200)' }}>
              <span className="badge badge-warn">
                {t('structure.unplaced')}: {tree.unplaced.count}
              </span>
            </div>
          )}
        </div>

        <div>
          {mode === 'add' && isAdmin && (
            <UnitForm mode="add" refs={refs} units={flat}
                      parentId={selected?.id ?? null}
                      onCancel={() => setMode(null)} onError={onError}
                      onSaved={() => afterChange(t('structure.unitCreated'))} />
          )}

          {mode === 'edit' && isAdmin && selected && (
            <UnitForm mode="edit" refs={refs} units={flat} unit={selected}
                      onCancel={() => setMode(null)} onError={onError}
                      onSaved={() => afterChange(t('common.saved'))} />
          )}

          {!mode && (!selected ? (
            <div className="card"><div className="empty">
              {t('common.select')}
            </div></div>
          ) : (
            <>
              <UnitDetail key={selected.id} unit={selected} isAdmin={isAdmin} t={t} pick={pick}
                          units={flat} positions={refs.positions || []} onChanged={() => load(true)}
                          onEdit={() => setMode('edit')}
                          onAddChild={() => setMode('add')}
                          onError={onError}
                          onDeleted={() => {
                            setSelected(null)
                            afterChange(t('structure.unitDeleted'))
                          }} />
              <StaffingTable unitId={selected.id} unitName={pick(selected)}
                             onChanged={() => load(true)} />
            </>
          ))}
        </div>
      </div>
    </>
  )
}

function UnitDetail({ unit, isAdmin, t, pick, onEdit, onAddChild, onDeleted,
                      onError, positions, units, onChanged }) {
  const { lang } = useI18n()
  const l = worklistText[lang] || worklistText.ru
  const [usage, setUsage] = useState(null)
  const [members, setMembers] = useState(null)
  const [membersError, setMembersError] = useState(null)
  const [previewId, setPreviewId] = useState(null)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [transfer, setTransfer] = useState(null)
  const [refresh, setRefresh] = useState(0)
  const query = useDebounced(search)
  useEffect(() => {
    let active = true
    setUsage(null)
    if (isAdmin) api.unitUsage(unit.id).then(r => { if (active) setUsage(r.data) })
      .catch(e => { if (active) onError(errorMessage(e)) })
    return () => { active = false }
  }, [unit.id, unit.own_count, unit.staffing_lines, isAdmin, refresh, onError])
  useEffect(() => {
    let active = true
    setMembers(null)
    setMembersError(null)
    api.orgUnitMembers(unit.id, { offset, limit: 15, q: query })
      .then(({ data }) => {
        if (!active) return
        if (offset && offset >= data.total) {
          setOffset(Math.max(0, (Math.ceil(data.total / 15) - 1) * 15))
        } else {
          setMembers(data)
        }
      })
      .catch(e => { if (active) setMembersError(errorMessage(e)) })
    return () => { active = false }
  }, [unit.id, unit.own_count, offset, query, refresh])
  const remove = async () => {
    if (!window.confirm(t('structure.deleteWarn'))) return
    onError(null)
    try { await api.unitDelete(unit.id); onDeleted() }
    catch (e) { onError(errorMessage(e)) }
  }
  return <div className="card flush">
    <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--slate-200)' }}>
      <div className="worklist-toolbar" style={{ justifyContent: 'space-between' }}>
        <div><strong>{pick(unit)}</strong><div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          <span className="mono">{unit.code}</span> · {pick(unit, 'unit_type')}{unit.region ? ` · ${unit.region}` : ''}
        </div><div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
          {t('structure.own')}: {unit.own_count} · {t('structure.total')}: {unit.total_count}
        </div>
          <a className="structure-unit-ranking" href={`#/analytics?tab=ranking&unit=${unit.id}`}>
            {l.unitRanking} <span aria-hidden="true">→</span>
          </a>
        </div>
        {isAdmin && <div className="btn-row">
          <button className="btn btn-ghost btn-sm" onClick={onEdit}>{t('edit.edit')}</button>
          <button className="btn btn-ghost btn-sm" onClick={onAddChild}>+ {t('structure.addChild')}</button>
          <button className="btn btn-danger btn-sm" disabled={!usage?.can_delete}
            title={usage && !usage.can_delete ? t('structure.cannotDelete') : ''} onClick={remove}>{t('common.delete')}</button>
        </div>}
      </div>
      {isAdmin && usage && !usage.can_delete && <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
        {t('structure.cannotDelete')} — {t('structure.children')}: {usage.children}, {t('structure.employees')}: {usage.employees},
        {' '}{t('structure.postings')}: {usage.work_experience_rows}, {t('vacancy.title')}: {usage.vacancies}, {l.staffingRows}: {usage.staffing_lines}{usage.disposal_periods > 0 && <>, {l.disposalPeriods}: {usage.disposal_periods}</>}.
      </div>}
    </div>
    {isAdmin && <details className="structure-guide" style={{ paddingTop: 12 }}><summary>{l.changeStructure}</summary>
      <ol><li>{l.changeGuide1}</li><li>{l.changeGuide2}</li><li>{l.changeGuide3}</li></ol>
    </details>}
    <div className="structure-members-toolbar worklist-toolbar">
      <strong style={{ fontSize: 13 }}>{l.unitPeople}</strong>
      <input type="search" aria-label={l.findPeople} placeholder={l.findPeople} value={search} maxLength={200}
        onChange={e => { setSearch(e.target.value); setOffset(0); setPreviewId(null) }} />
    </div>
    {membersError ? <div className="alert alert-bad" role="alert">{membersError}{' '}
      <button className="btn btn-ghost btn-sm" onClick={() => setRefresh(value => value + 1)}>{t('errors.retry')}</button>
    </div> : !members ? <div role="status" aria-label={t('common.loading')} className="spinner" /> : <>
      <div className="worklist-table-scroll"><table><thead><tr><th>{t('employee.fullName')}</th><th>{t('employee.position')}</th>{isAdmin && <th />}</tr></thead>
        <tbody>{members.data.length === 0 ? <tr><td colSpan={isAdmin ? 3 : 2}><div className="empty">{search ? l.noResults : t('structure.noEmployees')}</div></td></tr>
          : members.data.map(e => <MemberRows key={e.id} employee={e} open={previewId === e.id}
              onToggle={() => setPreviewId(previewId === e.id ? null : e.id)}
              onTransfer={isAdmin ? () => { if (confirmUnsavedLeave(appointmentScope)) setTransfer(e) } : null} />)}</tbody></table></div>
      <WorklistPager total={members.total} offset={offset} limit={15}
        onChange={next => { setPreviewId(null); setOffset(next) }} />
    </>}
    {isAdmin && transfer && <section className="structure-transfer">
      <div className="worklist-toolbar" style={{ justifyContent: 'space-between' }}><h3>{transfer.full_name}</h3>
        <button className="btn btn-ghost btn-sm" onClick={() => { if (confirmUnsavedLeave(appointmentScope)) setTransfer(null) }}>{l.close}</button></div>
      <AppointmentPanel key={transfer.id} employeeId={transfer.id} positions={positions} orgUnits={units}
        onError={onError} onChanged={() => { setTransfer(null); setOffset(0); setRefresh(value => value + 1); onChanged?.() }} />
    </section>}
  </div>
}

function MemberRows({ employee, open, onToggle, onTransfer }) {
  const { t, pick, lang } = useI18n()
  const l = worklistText[lang]
  const panelId = `structure-person-${employee.id}`
  const name = employee.full_name || employee.anonymous_code
  const status = employee.profile_status
  return <>
    <tr className={open ? 'active' : undefined}>
      <td><button type="button" className="structure-person-name" aria-expanded={open}
        aria-controls={open ? panelId : undefined} onClick={onToggle} title={l.miniProfile}>
        <span className="structure-person-chevron" aria-hidden="true" />{name}
      </button>
        {!open && <small className="structure-person-meta mono">{employee.personnel_number || employee.anonymous_code}</small>}
      </td>
      <td>{pick(employee, 'position') || '—'}
        {!open && employee.since && <small className="structure-person-meta"><time dateTime={employee.since}>{employee.since}</time></small>}
      </td>
      {onTransfer && <td><button className="btn btn-ghost btn-sm" onClick={onTransfer}>{t('appointment.type')}</button></td>}
    </tr>
    {open && <tr><td className="structure-person-detail" colSpan={onTransfer ? 3 : 2}>
      <section id={panelId} aria-label={`${l.miniProfile} · ${name}`}>
        <dl>
          <div><dt>{t('employee.personnelNumber')}</dt><dd>{employee.personnel_number || '—'}</dd></div>
          <div><dt>{t('employee.anonymousCode')}</dt><dd>{employee.anonymous_code || '—'}</dd></div>
          <div><dt>{l.postingStart}</dt><dd>{employee.since ? <time dateTime={employee.since}>
            {new Date(employee.since + 'T00:00:00Z').toLocaleDateString(lang === 'kk' ? 'kk-KZ' : 'ru-RU', { timeZone: 'UTC' })}
          </time> : '—'}</dd></div>
          <div><dt>{t('employee.profileStatus')}</dt><dd>{status ? <span className={`badge ${status === 'verified' ? 'badge-ok' : status === 'archived' ? 'badge-closed' : 'badge-warn'}`}>
            {t(`employee.status.${status}`)}</span> : '—'}</dd></div>
        </dl>
        <a href={`#/employees?employee=${employee.id}`} target="_blank" rel="noopener noreferrer">
          {l.openDossierTab} <span aria-hidden="true">↗</span></a>
      </section>
    </td></tr>}
  </>
}

const ROOT = '__root__'

function UnitForm({ mode, unit, parentId, refs, units, onSaved, onCancel,
                    onError }) {
  const { t, pick } = useI18n()
  const editing = mode === 'edit'
  // A unit cannot move under itself or anything below it, so those are left
  // out of the list rather than offered and then refused.
  const descendants = React.useMemo(() => {
    const found = new Set()
    if (!editing) return found
    const byParent = new Map()
    units.forEach((u) => {
      const list = byParent.get(u.parent_id) || []
      list.push(u)
      byParent.set(u.parent_id, list)
    })
    const walk = (id) => (byParent.get(id) || []).forEach((c) => {
      if (found.has(c.id)) return
      found.add(c.id)
      walk(c.id)
    })
    walk(unit.id)
    return found
  }, [editing, unit, units])

  const [form, setForm] = useState(() => ({
    code: editing ? unit.code : '',
    name_ru: editing ? unit.name_ru : '',
    name_kk: editing ? (unit.name_kk || '') : '',
    name_en: editing ? (unit.name_en || '') : '',
    region: editing ? (unit.region || '') : '',
    unit_type_id: editing && unit.unit_type_id ? String(unit.unit_type_id) : '',
    country_id: editing && unit.country_id ? String(unit.country_id) : '',
    parent_id: editing ? '' : (parentId ?? ''),
  }))
  const [busy, setBusy] = useState(false)

  const submit = async (ev) => {
    ev.preventDefault()
    onError(null)
    setBusy(true)

    const body = {
      code: form.code.trim(),
      name_ru: form.name_ru.trim(),
      name_kk: form.name_kk.trim() || null,
      name_en: form.name_en.trim() || null,
      region: form.region.trim() || null,
      unit_type_id: form.unit_type_id ? Number(form.unit_type_id) : null,
      country_id: form.country_id ? Number(form.country_id) : null,
    }

    try {
      if (editing) {
        await api.refUpdate('org-units', unit.id, body)
      } else {
        body.parent_id = form.parent_id ? Number(form.parent_id) : null
        await api.refCreate('org-units', body)
      }
      onSaved()
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const reparent = async (value) => {
    onError(null)
    try {
      await api.unitMove(unit.id, value === null ? null : Number(value))
      onSaved()
    } catch (e) {
      onError(errorMessage(e))
    }
  }

  return (
    <div className="card">
      <h3>{editing ? t('structure.editUnit') : t('structure.addUnit')}</h3>
      <form onSubmit={submit}>
        <div className="form-row">
          <div className="field">
            <label>{t('common.code')}</label>
            <input value={form.code} required disabled={editing}
                   placeholder="UNIT_15"
                   onChange={(e) => setForm({ ...form,
                     code: e.target.value.toUpperCase() })} />
            {editing && (
              <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>
                {t('structure.codeLocked')}
              </div>
            )}
          </div>
          <div className="field">
            <label>{t('catalogs.nameRu')}</label>
            <input value={form.name_ru} required
                   onChange={(e) => setForm({ ...form,
                     name_ru: e.target.value })} />
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label>{t('catalogs.nameKk')}</label>
            <input value={form.name_kk}
                   onChange={(e) => setForm({ ...form,
                     name_kk: e.target.value })} />
          </div>
        </div>

        <div className="form-row-3">
          <div className="field">
            <label>{t('employee.career.unitType')}</label>
            <select value={form.unit_type_id} required
                    onChange={(e) => setForm({ ...form,
                      unit_type_id: e.target.value })}>
              <option value="">—</option>
              {(refs['org-unit-types'] || []).map((o) => (
                <option key={o.id} value={o.id}>{pick(o)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t('employee.career.country')}</label>
            <select value={form.country_id}
                    onChange={(e) => setForm({ ...form,
                      country_id: e.target.value })}>
              <option value="">—</option>
              {(refs.countries || []).map((o) => (
                <option key={o.id} value={o.id}>{pick(o)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t('structure.region')}</label>
            <input value={form.region}
                   onChange={(e) => setForm({ ...form,
                     region: e.target.value })} />
          </div>
        </div>

        {!editing && (
          <div className="field">
            <label>{t('structure.parent')}</label>
            <select value={form.parent_id}
                    onChange={(e) => setForm({ ...form,
                      parent_id: e.target.value })}>
              <option value="">{t('structure.noParent')}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>{pick(u)}</option>
              ))}
            </select>
          </div>
        )}

        <div className="btn-row">
          <button className="btn" type="submit" disabled={busy}>
            {t('common.save')}
          </button>
          <button className="btn btn-ghost" type="button" onClick={onCancel}>
            {t('common.cancel')}
          </button>
        </div>
      </form>

      {editing && (
        <div style={{ marginTop: 16, paddingTop: 14,
                      borderTop: '1px solid var(--slate-200)' }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>{t('structure.moveTo')}</label>
            <select value="" onChange={(e) => {
                      if (!e.target.value) return
                      reparent(e.target.value === ROOT ? null : e.target.value)
                    }}>
              <option value="">{t('structure.chooseParent')}</option>
              <option value={ROOT}>{t('structure.noParent')}</option>
              {units.filter((u) => u.id !== unit.id
                                   && !descendants.has(u.id)).map((u) => (
                <option key={u.id} value={u.id}>{pick(u)}</option>
              ))}
            </select>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
              {t('structure.moveHint')}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* --------------------------------------------------------------- segments */

function Segments({ onError }) {
  const { t, pick, lang } = useI18n()
  const l = worklistText[lang] || worklistText.ru
  const [segments, setSegments] = useState([])
  const [code, setCode] = useState('all')
  const [members, setMembers] = useState(null)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const query = useDebounced(search)
  useEffect(() => {
    let active = true
    api.segments().then(r => { if (active) setSegments(r.data.data) })
      .catch(e => { if (active) onError(errorMessage(e)) })
    return () => { active = false }
  }, [onError])
  useEffect(() => {
    let active = true
    setMembers(null)
    api.segmentMembers(code, { offset, limit: 20, q: query })
      .then(r => { if (active) setMembers(r.data) })
      .catch(e => { if (active) onError(errorMessage(e)) })
    return () => { active = false }
  }, [code, offset, query, onError])
  return <>
    <div className="structure-segments" role="group" aria-label={t('structure.segmentsTab')}>
      {segments.map(segment => <button key={segment.code} className={`btn btn-sm ${code === segment.code ? '' : 'btn-ghost'}`}
        aria-pressed={code === segment.code} onClick={() => { setCode(segment.code); setOffset(0) }}>
        {pick(segment)} <span className="badge badge-mute">{segment.count}</span>
      </button>)}
    </div>
    <div className="card flush">
      <div className="structure-members-toolbar worklist-toolbar">
        <input type="search" aria-label={l.segmentSearch} placeholder={l.findPeople} value={search}
          onChange={e => { setSearch(e.target.value); setOffset(0) }} />
      </div>
      {!members ? <div className="spinner" /> : <>
        <div className="worklist-table-scroll"><table><thead><tr>
          <th>{t('employee.fullName')}</th><th>{t('employee.position')}</th><th>{t('employee.orgUnit')}</th><th>{t('structure.since')}</th>
        </tr></thead><tbody>
          {members.data.length === 0 ? <tr><td colSpan={4}><div className="empty">{l.noResults}</div></td></tr> : members.data.map(e =>
            <tr key={e.id}><td><strong>{e.full_name}</strong><div className="muted mono" style={{ fontSize: 11 }}>{e.personnel_number || e.anonymous_code}</div></td>
              <td>{pick(e, 'position') || '—'}</td><td>{pick(e, 'org_unit') || '—'}</td><td>{e.since || '—'}</td></tr>)}
        </tbody></table></div>
        <WorklistPager total={members.count} offset={offset} limit={20} onChange={setOffset} />
      </>}
    </div>
  </>
}
