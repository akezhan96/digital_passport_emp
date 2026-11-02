import React, { useEffect, useRef, useState } from 'react'
import { dossierSubsectionsApi as api } from '../dossierSubsectionsApi'
import { errorMessage } from '../api'
import { customTabId, profileHref } from '../appRoute'
import { useI18n } from '../i18n'
import { dossierSubsectionText } from '../i18n/dossierSubsections'
import DossierTabEditor from './DossierTabEditor'
import './dossierSubsections.css'

// Old versions allowed identical names in different sections. Preserve both
// tab identities and show their previous section only when a name collides.
function tabName(tab, tabs, builtins, pick, t) {
  const name = pick(tab)
  const duplicate = tabs.some(other => other.id !== tab.id && pick(other) === name)
    || builtins.some(item => item.label === name)
  if (!duplicate) return name
  return tab.tab === 'custom' ? `${name} · #${tab.id}` : `${name} · ${t(`employee.tabs.${tab.tab}`)}`
}

function RequestError({ error, retry, copy }) {
  return error && <div className="alert alert-bad" role="alert">{errorMessage(error)}{' '}
    {retry && <button type="button" className="btn btn-sm btn-ghost" onClick={retry}>{copy.retry}</button>}</div>
}

function TabStrip({ children, selectedTab, isAdmin, manage, onCreate, onManage, copy }) {
  const track = useRef(null)
  const [scroll, setScroll] = useState({ left: false, right: false })
  function updateBounds() {
    const node = track.current
    if (!node) return
    const left = node.scrollLeft > 1
    const right = node.scrollWidth - node.clientWidth - node.scrollLeft > 1
    setScroll(old => old.left === left && old.right === right ? old : { left, right })
  }
  function showSelected() {
    const node = track.current
    const active = node?.querySelector('[aria-current="page"]')
    if (!node || !active) return
    const bounds = node.getBoundingClientRect(), rect = active.getBoundingClientRect()
    if (rect.left < bounds.left) node.scrollLeft += rect.left - bounds.left
    else if (rect.right > bounds.right) node.scrollLeft += rect.right - bounds.right
    updateBounds()
  }
  useEffect(() => {
    const node = track.current
    const observer = new ResizeObserver(() => { showSelected(); updateBounds() })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  // Visibility can change when tab metadata arrives or labels change language.
  useEffect(() => { showSelected(); updateBounds() }, [selectedTab, children])
  function step(direction) {
    const node = track.current
    node.scrollBy({ left: direction * Math.max(100, node.clientWidth * .7), behavior: 'smooth' })
  }
  return <nav className="dossier-tab-strip" aria-label={copy.nav}>
    <div ref={track} className="tabs employee-profile-tabs dossier-tab-track" onScroll={updateBounds}>{children}</div>
    <div className="dossier-tab-tools">
      {(scroll.left || scroll.right) && <>
        <button type="button" className="btn btn-sm btn-ghost dossier-tab-step" aria-label={copy.left} title={copy.left}
          disabled={!scroll.left} onClick={() => step(-1)}>‹</button>
        <button type="button" className="btn btn-sm btn-ghost dossier-tab-step" aria-label={copy.right} title={copy.right}
          disabled={!scroll.right} onClick={() => step(1)}>›</button>
      </>}
      {isAdmin && <>
        <button type="button" className="btn btn-sm btn-ghost dossier-tab-action" aria-label={'+ ' + copy.addTab} title={copy.addTab}
          onClick={onCreate}><span aria-hidden="true">＋</span><span className="dossier-tool-label">{copy.addTab}</span></button>
        <button type="button" className="btn btn-sm btn-ghost dossier-tab-action" aria-label={copy.manageTabs} title={copy.manageTabs}
          aria-expanded={manage} onClick={onManage}><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M3 7h5m5 0h8M3 17h10m5 0h3"/><circle cx="10.5" cy="7" r="2.5"/><circle cx="15.5" cy="17" r="2.5"/></svg></button>
      </>}
    </div></nav>
}

export default function DossierTabs({ employeeId, isAdmin, archivedProfile, selectedTab, routeKey, builtins, children }) {
  const { lang, pick, t } = useI18n()
  const copy = dossierSubsectionText(lang)
  const id = customTabId(selectedTab)
  const [tabs, setTabs] = useState(null)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState(null)
  const [manage, setManage] = useState(false)
  const [dialog, setDialog] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const refreshTabs = () => setRefresh(n => n + 1)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    api.tabs(isAdmin, controller.signal).then(({data}) => {
      if (!controller.signal.aborted) setTabs(data.data)
    }).catch(e => { if (!controller.signal.aborted) { setTabs(null); setError(e) } })
    return () => controller.abort()
  }, [isAdmin, refresh])
  const visible = (tabs || []).filter(tab => (isAdmin || tab.visibility !== 'admin') && tab.is_active)
  const active = visible.find(tab => tab.id === id)
  function savedTab(row) {
    setDialog(null); setActionError(null)
    setTabs(previous => [...(previous || []).filter(tab => tab.id !== row.id), row].sort((a, b) => a.id - b.id))
    if (!dialog?.row) {
      setManage(false)
      location.hash = profileHref(routeKey, employeeId, `custom-${row.id}`)
    }
  }
  async function toggle(tab) {
    if (tab.is_active && !window.confirm(copy.archiveTab.replace('{name}', pick(tab)))) return
    setBusy(true); setActionError(null)
    try {
      const {data} = await api.editTab(tab.id, { is_active: !tab.is_active, expected_revision: tab.revision })
      setTabs(rows => rows.map(row => row.id === data.id ? data : row))
      if (id === tab.id && !data.is_active) location.hash = profileHref(routeKey, employeeId)
    } catch (e) { setActionError(e); refreshTabs() } finally { setBusy(false) }
  }
  const tabLink = (key, label) => <a key={key} className={`tab ${selectedTab === key ? 'active' : ''}`}
    aria-current={selectedTab === key ? 'page' : undefined} href={profileHref(routeKey, employeeId, key)} title={label}><span className="dossier-tab-label">{label}</span></a>
  return <>
    <TabStrip selectedTab={selectedTab} isAdmin={isAdmin} manage={manage} copy={copy}
      onCreate={() => { setActionError(null); setDialog({ row: null }) }}
      onManage={() => { setManage(value => !value); setActionError(null) }}>
      {builtins.map(item => tabLink(item.key, item.label))}
      {visible.map(tab => tabLink(`custom-${tab.id}`, tabName(tab, visible, builtins, pick, t)))}
    </TabStrip>
    <RequestError error={error} retry={refreshTabs} copy={copy} />
    {manage && isAdmin && <section className="card dossier-tab-settings">
      <div className="dossier-panel-heading"><h3>{copy.manageTabs}</h3><button className="btn btn-ghost btn-sm" onClick={() => setManage(false)}>{copy.done}</button></div>
      {!tabs && !error && <p className="muted" role="status">{copy.loading}</p>}
      {tabs && !tabs.length && <p className="muted">{copy.emptyTabs}</p>}
      {(tabs || []).map(tab => <div key={tab.id} className="dossier-setting-row"><span><strong>{tabName(tab,tabs,builtins,pick,t)}</strong>
        {tab.visibility === 'admin' && <small>{copy.privateLabel}</small>}{!tab.is_active && <small>{copy.archived}</small>}</span>
        <div className="btn-row"><button disabled={busy} className="btn btn-ghost btn-sm" onClick={() => setDialog({ row: tab })}>{copy.edit}</button>
          <button disabled={busy} className="btn btn-ghost btn-sm" onClick={() => toggle(tab)}>{tab.is_active ? copy.archive : copy.restore}</button></div></div>)}
      <RequestError error={actionError} copy={copy} />
    </section>}
    {!id ? children : active ? <DossierTabContent key={id} employeeId={employeeId} tab={active} isAdmin={isAdmin} archivedProfile={archivedProfile} onMetadataChanged={refreshTabs}/>
      : tabs ? <div className="card"><p>{copy.unavailable}</p><a href={profileHref(routeKey, employeeId)}>{copy.backGeneral}</a></div>
      : !error && <p role="status">{copy.loading}</p>}
    {dialog && <DossierTabEditor kind="tab" row={dialog.row} onSaved={savedTab}
      onClose={reload => { setDialog(null); if (reload) refreshTabs() }} />}
  </>
}

function displayValue(field, value, lang, copy) {
  if (value == null || value === '') return '—'
  if (field.field_type === 'boolean') return value ? copy.yes : copy.no
  const locale = lang === 'kk' ? 'kk-KZ' : 'ru-RU'
  if (field.field_type === 'date') return new Intl.DateTimeFormat(locale,{timeZone:'UTC'}).format(new Date(value + 'T00:00:00Z'))
  if (field.field_type === 'number') return new Intl.NumberFormat(locale,{maximumFractionDigits:4}).format(value)
  return String(value)
}

export function EntryCard({ entry, fields, canEdit, disabled, edit, remove }) {
  const { lang, pick } = useI18n()
  const copy = dossierSubsectionText(lang)
  return <article className="dossier-tab-entry">
    <header><strong>{entry.title || `${copy.entry} №${entry.id}`}</strong>
      {canEdit && <div className="btn-row"><button className="btn btn-ghost btn-sm" disabled={disabled} onClick={edit}>{copy.edit}</button>
        <button className="btn btn-ghost btn-sm danger" disabled={disabled} onClick={remove}>{copy.remove}</button></div>}</header>
    {entry.description && <p className="dossier-entry-description">{entry.description}</p>}
    {fields.length > 0 && <dl>{fields.map(field => <div key={field.id}><dt>{pick(field)}</dt>
      <dd>{displayValue(field,entry.values?.[field.id],lang,copy)}</dd></div>)}</dl>}
  </article>
}

function DossierTabContent({ employeeId, tab, isAdmin, archivedProfile, onMetadataChanged }) {
  const { lang, pick } = useI18n()
  const copy = dossierSubsectionText(lang)
  const [data, setData] = useState(null)
  const [manage, setManage] = useState(false)
  const [draft, setDraft] = useState(null)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const reload = () => setRefresh(n => n + 1)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    api.detail(employeeId, tab.id, isAdmin, controller.signal).then(({data}) => {
      if (!controller.signal.aborted) setData(data)
    }).catch(e => {
      if (controller.signal.aborted) return
      setData(null); setError(e)
      if (e.response?.status === 404 || e.response?.status === 403) onMetadataChanged()
    })
    return () => controller.abort()
  }, [employeeId,tab.id,isAdmin,refresh])
  const fields = data?.fields || []
  const activeFields = fields.filter(field => field.is_active)
  function open(kind, row = null) { setNotice(false); setActionError(null); setDraft({ kind, row }) }
  function saved() { if (draft.kind === 'field') setManage(true); setDraft(null); setNotice(true); reload() }
  async function act(work) {
    if (busy) return
    setBusy(true); setActionError(null); setNotice(false)
    try { await work(); setNotice(true); reload() } catch (e) { setActionError(e); reload() } finally { setBusy(false) }
  }
  function toggleField(field) {
    if (field.is_active && !window.confirm(copy.archiveField.replace('{name}',pick(field)))) return
    act(() => api.editField(tab.id,field.id,{is_active:!field.is_active,expected_revision:field.revision}))
  }
  function removeEntry(entry) {
    if (window.confirm(copy.deleteEntry.replace('{name}',entry.title || `${copy.entry} №${entry.id}`))) {
      act(() => api.removeEntry(employeeId,tab.id,entry.id,entry.revision))
    }
  }
  const canFill = isAdmin && !archivedProfile
  return <section className="card dossier-tab-panel" aria-labelledby="dossier-tab-title">
    <div className="dossier-panel-heading"><div><h3 id="dossier-tab-title">{pick(tab)}</h3>
      {tab.visibility === 'admin' && <small className="muted">{copy.privateLabel}</small>}</div>
      {data && isAdmin && <div className="btn-row"><button className="btn btn-ghost btn-sm" aria-expanded={manage}
        onClick={() => setManage(!manage)}>{copy.manageFields}</button>
        {canFill && <button className="btn btn-sm" disabled={busy} onClick={() => open('entry')}>+ {copy.addEntry}</button>}</div>}</div>
    <RequestError error={error} retry={reload} copy={copy} />
    <RequestError error={actionError} copy={copy} />
    {notice && <span className="dossier-saved" role="status">{copy.saved}</span>}
    {!error && !data && <p className="muted" role="status">{copy.loading}</p>}
    {data && <>
      {isAdmin && (manage || !activeFields.length) && <section className="dossier-field-settings">
        <div className="dossier-panel-heading"><strong>{copy.fields}</strong><button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => open('field')}>+ {copy.addField}</button></div>
        <p className="muted">{activeFields.length ? copy.fieldHint : copy.emptyFields}</p>
        {manage && fields.map(field => <div key={field.id} className="dossier-setting-row"><span><strong>{pick(field)}</strong>
          <small>{copy[field.field_type]}</small>{!field.is_active && <small>{copy.archived}</small>}</span>
          <div className="btn-row"><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => open('field',field)}>{copy.edit}</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => toggleField(field)}>{field.is_active ? copy.archive : copy.restore}</button></div></div>)}
      </section>}
      {isAdmin && archivedProfile && <p className="muted">{copy.archivedProfile}</p>}
      <h4>{copy.entries} <span className="dossier-count">{data.entries.length}</span></h4>
      {!data.entries.length && <p className="empty">{copy.noEntries}</p>}
      {data.entries.map(entry => <EntryCard key={entry.id} entry={entry} fields={activeFields} canEdit={canFill} disabled={busy}
        edit={() => open('entry',entry)} remove={() => removeEntry(entry)} />)}
    </>}
    {draft && <DossierTabEditor {...draft} employeeId={employeeId} sectionId={tab.id} fields={fields}
      onClose={again => { setDraft(null); if (again) reload() }} onSaved={saved} />}
  </section>
}

