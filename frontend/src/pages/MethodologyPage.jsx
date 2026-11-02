import React, { useEffect, useRef, useState } from 'react'
import { candidateApi } from '../candidateApi'
import { errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { candidateText } from '../i18n/candidateMethodology'
import CandidateEvaluation, { formatPoints } from '../components/CandidateEvaluation'
import CandidateSourceEditor from '../components/CandidateSourceEditor'
import { DossierFieldManager } from '../components/DossierFields'
import { hasDossierSource, sourceDefinition, sourceLabel, methodologySections, criterionSection, orderedCriteria, moveItem } from '../candidateSources'
import { renameMethodologyItem, methodologyUpdatePayload, saveRenamedVersion } from '../methodologyEditing'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { CANDIDATE_SCOPE, METHODOLOGY_SCOPE, confirmUnsavedLeave, runAfterUnsavedConfirmation } from '../unsavedChanges'
import '../candidate-methodology.css'

export default function MethodologyPage() {
  const { lang, pick } = useI18n(), { isAdmin } = useAuth(), copy = candidateText(lang)
  const [models, setModels] = useState([]), [selected, setSelected] = useState(null), [method, setMethod] = useState(null)
  const [tab, setTab] = useState('criteria'), [sectionKey, setSectionKey] = useState(null)
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(null)
  const [refresh, setRefresh] = useState(0), [sources, setSources] = useState(null), [sourceRefresh, setSourceRefresh] = useState(0)
  const [expanded, setExpanded] = useState(null), [creating, setCreating] = useState(false), [loaded, setLoaded] = useState(false)
  const [renaming, setRenaming] = useState(null), [renameError, setRenameError] = useState(null), [notice, setNotice] = useState(null)
  const renameDraft = useRef(null), pendingFocus = useRef(null), renameFocus = useRef(null)
  const sectionTitle = useRef(null), criterionTitle = useRef(null)
  const markSaved = useUnsavedChanges(dirty, copy.discard, METHODOLOGY_SCOPE)
  useEffect(() => {
    let active = true
    candidateApi.models().then(({ data }) => {
      if (!active) return
      setModels(data); setLoaded(true)
      setSelected(previous => data.some(m => m.id === previous) ? previous : data.find(m => m.status === 'active')?.id ?? data[0]?.id ?? null)
    }).catch(e => { if (active) { setError(errorMessage(e)); setLoaded(true) } })
    return () => { active = false }
  }, [refresh])
  useEffect(() => {
    const controller = new AbortController()
    candidateApi.sources(controller.signal).then(({ data }) => { if (!controller.signal.aborted) setSources(data) })
      .catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
    return () => controller.abort()
  }, [sourceRefresh])
  useEffect(() => {
    if (!selected) { setMethod(null); return }
    const controller = new AbortController()
    setMethod(null); setError(null); setExpanded(null)
    candidateApi.model(selected, controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) {
        const focus = pendingFocus.current?.id === data.id ? pendingFocus.current : null
        pendingFocus.current = null
        if (focus) renameFocus.current = focus
        setMethod(data); setDirty(false); setSectionKey(focus?.sectionKey ?? methodologySections(data)[0]?.key ?? null); setExpanded(focus?.position ?? null)
      }
    }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
    return () => controller.abort()
  }, [selected])
  useEffect(() => {
    const target = renameFocus.current
    if (renaming || tab !== 'criteria' || !method || target?.id !== method.id) return
    const element = target.position != null ? criterionTitle.current : sectionTitle.current
    if (element) {
      element.focus({ preventScroll: true }); element.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      renameFocus.current = null
    }
  }, [method, sectionKey, expanded, renaming, tab])
  const locked = !isAdmin || method?.status !== 'draft'
  const sections = methodologySections(method), section = sections.find(s => s.key === sectionKey) || sections[0]
  const criteria = orderedCriteria(method, section?.key)
  const update = fn => { setMethod(fn); setDirty(true) }
  const change = (position, key, value) => update(old => ({ ...old, criteria: old.criteria.map(c => c.position === position ? { ...c, [key]: value } : c) }))
  const accept = (next, focus = null) => {
    if (focus?.position != null) {
      const item = next.criteria.find(criterion => criterion.position === focus.position)
      if (item) focus = { ...focus, sectionKey: criterionSection(item) }
    }
    pendingFocus.current = next.id !== selected && focus ? { id: next.id, ...focus } : null
    renameFocus.current = next.id === selected && focus ? { id: next.id, ...focus } : null
    markSaved(); setDirty(false); setNotice(null); setMethod(next); setSelected(next.id); setTab('criteria'); setExpanded(focus?.position ?? null)
    setSectionKey(focus?.sectionKey ?? methodologySections(next)[0]?.key ?? null); setModels(old => [next, ...old.filter(m => m.id !== next.id)])
  }
  const choose = id => {
    if (busy || !confirmUnsavedLeave(METHODOLOGY_SCOPE)) return
    pendingFocus.current = null; renameFocus.current = null
    markSaved(); setDirty(false); setNotice(null); setSelected(Number(id))
  }
  const clone = async () => {
    if (!confirmUnsavedLeave(METHODOLOGY_SCOPE)) return
    setBusy(true); setError(null)
    try { accept((await candidateApi.clone(method.id)).data) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const removeMethod = async () => {
    if (!window.confirm(`${copy.deleteMethodConfirm}\n«${pick(method)}»`)) return
    setBusy(true); setError(null); setNotice(null)
    try { await candidateApi.remove(method.id); markSaved(); setDirty(false); setMethod(null); setSelected(null); setRefresh(x => x + 1) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const save = async event => {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const { data } = await candidateApi.update(method.id, methodologyUpdatePayload(method))
      markSaved(); setMethod(data); setDirty(false); setNotice(null); setRefresh(x => x + 1)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const activate = async () => {
    if (!window.confirm(copy.activateConfirm)) return
    setBusy(true); setError(null)
    try { const { data } = await candidateApi.activate(method.id, method.revision); setMethod(data); setRefresh(x => x + 1) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const addSection = () => {
    const next = { key: `section_${globalThis.crypto.randomUUID().replaceAll('-', '')}`, name_ru: 'Новый раздел', name_kk: 'Жаңа бөлім', kind: 'general', position: sections.length }
    update(old => ({ ...old, sections: [...sections, next] })); setSectionKey(next.key); setExpanded(null)
  }
  const changeSection = (key, value) => {
    if (key === 'kind' && value === 'psychological' && criteria.some(hasDossierSource) && !window.confirm(copy.psychologyManualConfirm)) return
    update(old => ({ ...old, sections: sections.map(s => s.key === section.key ? { ...s, [key]: value } : s),
      criteria: key === 'kind' ? old.criteria.map(c => criterionSection(c) === section.key ? { ...c, block: value, ...(value === 'psychological' ? { source: null } : {}) } : c) : old.criteria }))
  }
  const moveSection = direction => update(old => ({ ...old, sections: moveItem(sections, sections.findIndex(s => s.key === section.key), direction).map((s, i) => ({ ...s, position: i })) }))
  const removeSection = () => {
    if (!window.confirm(`${copy.removeSectionConfirm}\n«${pick(section)}» (${criteria.length})`)) return
    const next = sections.filter(s => s.key !== section.key)
    update(old => ({ ...old, sections: next.map((s, i) => ({ ...s, position: i })), criteria: old.criteria.filter(c => criterionSection(c) !== section.key) }))
    setSectionKey(next[0]?.key ?? null); setExpanded(null)
  }
  const addCriterion = () => {
    const position = Math.max(2, ...method.criteria.map(c => c.position)) + 1
    const next = { position, section_key: section.key, block: section.kind, display_order: Math.max(0, ...method.criteria.map(c => c.display_order ?? c.position)) + 1,
      name_ru: 'Новый показатель', name_kk: 'Жаңа көрсеткіш', max_points: 10, enabled: true, source: null }
    update(old => ({ ...old, criteria: [...old.criteria, next] })); setExpanded(position)
  }
  const moveCriterion = (position, direction) => {
    const moved = moveItem(criteria, criteria.findIndex(c => c.position === position), direction), orders = Object.fromEntries(moved.map((c, i) => [c.position, i]))
    update(old => ({ ...old, criteria: old.criteria.map(c => criterionSection(c) === section.key ? { ...c, display_order: orders[c.position] } : c) }))
  }
  const removeCriterion = criterion => {
    if (!window.confirm(`${copy.removeCriterionConfirm}\n«${pick(criterion)}»`)) return
    update(old => ({ ...old, criteria: old.criteria.filter(c => c.position !== criterion.position) })); if (expanded === criterion.position) setExpanded(null)
  }
  const transferCriterion = (criterion, targetKey) => {
    const target = sections.find(s => s.key === targetKey)
    if (!target || target.key === criterionSection(criterion)) return
    if (target.kind === 'psychological' && hasDossierSource(criterion) && !window.confirm(copy.psychologyManualConfirm)) return
    const order = Math.max(0, ...orderedCriteria(method, target.key).map(c => c.display_order ?? c.position)) + 1
    update(old => ({ ...old, criteria: old.criteria.map(c => c.position === criterion.position
      ? { ...c, section_key: target.key, block: target.kind, display_order: order, ...(target.kind === 'psychological' ? { source: null } : {}) } : c) }))
    setSectionKey(target.key)
  }
  const startRename = (kind, item) => {
    renameDraft.current = null; setRenameError(null); setNotice(null)
    setRenaming({ kind, sectionKey: kind === 'section' ? item.key : criterionSection(item),
      position: kind === 'criterion' ? item.position : null, name_ru: item.name_ru, name_kk: item.name_kk,
      createVersion: method.status !== 'draft', hasDraft: false })
  }
  const closeRename = () => {
    if (renameDraft.current) setNotice(copy.renameDraftNotSaved)
    renameDraft.current = null; setRenaming(null); setRenameError(null)
  }
  const applyRename = async names => {
    const focus = { sectionKey: renaming.sectionKey, position: renaming.position }
    if (!renaming.createVersion) {
      const next = renameMethodologyItem(method, renaming, names)
      if (!next) { setRenameError(copy.renameTargetMissing); return false }
      renameFocus.current = { id: method.id, ...focus }
      update(() => next); setSectionKey(focus.sectionKey); setExpanded(focus.position)
      setNotice(copy.renamePendingSave); setRenaming(null)
      return true
    }
    setBusy(true); setRenameError(null)
    try {
      const next = await saveRenamedVersion(candidateApi, method, renaming, names, renameDraft.current, draft => { renameDraft.current = draft })
      accept(next, focus); renameDraft.current = null; setRenaming(null); setNotice(copy.renameVersionSaved)
      return true
    } catch (e) {
      if (renameDraft.current) { accept(renameDraft.current, focus); setRenaming(old => ({ ...old, hasDraft: true })) }
      setRenameError(e.code === 'RENAME_TARGET_MISSING' ? copy.renameTargetMissing : errorMessage(e))
      return false
    } finally { setBusy(false) }
  }
  return <div className="candidate-method">
    <div className="candidate-page-heading"><h1>{copy.title}</h1>{isAdmin && <button type="button" className="btn" disabled={busy || !loaded} onClick={() => { if (confirmUnsavedLeave(METHODOLOGY_SCOPE)) setCreating(true) }}>{copy.createMethod}</button>}</div>
    <div className="candidate-toolbar candidate-method-picker"><label>{copy.methodName}<select value={selected || ''} disabled={busy || !models.length} onChange={e => choose(e.target.value)}>
      {!models.length && <option value="">{copy.noMethod}</option>}{models.map(m => <option key={m.id} value={m.id}>{pick(m)} · {copy.version} {m.version} · {copy[m.status]}</option>)}</select></label>
      {isAdmin && method && <div className="candidate-row-actions"><button type="button" className="btn btn-ghost" disabled={busy} onClick={clone}>{method.status === 'draft' ? copy.copyMethod : copy.editVersion}</button>
        {method.status === 'draft' && <button type="button" className="btn btn-ghost candidate-danger" disabled={busy} onClick={removeMethod}>{copy.deleteDraft}</button>}</div>}
    </div>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    {notice && <p className="alert alert-info" role="status">{notice}</p>}
    <div className="candidate-tabs" role="group" aria-label={copy.title}>{['criteria', 'matrix', ...(isAdmin ? ['dossierFields'] : [])].map(key => <button key={key} type="button" className={tab === key ? 'active' : ''} aria-pressed={tab === key} onClick={() => setTab(key)}>{copy[key]}</button>)}</div>
    {isAdmin && <div hidden={tab !== 'dossierFields'}><DossierFieldManager onChanged={() => setSourceRefresh(x => x + 1)} /></div>}
    {tab !== 'dossierFields' && (!loaded ? <div className="spinner" /> : !models.length ? <p className="empty">{copy.startMethod}</p> : !method ? <div className="spinner" /> : <>
      {tab === 'matrix' ? <AssessmentMatrix methodologyId={method.id} refresh={refresh} /> : <form onSubmit={save}>
        <div className="candidate-method-meta"><span className={`badge ${method.status === 'active' ? 'badge-ok' : method.status === 'draft' ? 'badge-warn' : method.status === 'archived' ? 'badge-closed' : 'badge-mute'}`}>{copy[method.status]}</span><span>{copy.sections}: {sections.length} · {copy.criteria}: {method.criteria.length}</span>{method.status !== 'draft' && isAdmin && <span className="muted">{copy.immutable}</span>}</div>
        {!locked && <div className="candidate-method-names">{['ru', 'kk'].map(language => <label key={language}>{copy.methodName} · {language === 'ru' ? 'Русский' : 'Қазақша'}<input maxLength={200} required value={method[`name_${language}`]} disabled={busy} onChange={e => update(old => ({ ...old, [`name_${language}`]: e.target.value }))} /></label>)}</div>}
        <div className="candidate-constructor"><aside className="candidate-section-nav" aria-label={copy.sections}>
          <div className="candidate-section-nav-heading"><strong>{copy.sections}</strong>{!locked && <button type="button" className="btn btn-ghost btn-sm" disabled={busy || sections.length >= 50} onClick={addSection}>{copy.addSection}</button>}</div>
          {sections.map(s => <button type="button" key={s.key} className={`candidate-section-button ${section?.key === s.key ? 'active' : ''}`} aria-pressed={section?.key === s.key} onClick={() => { setSectionKey(s.key); setExpanded(null) }}><span>{pick(s)}</span><small>{method.criteria.filter(c => criterionSection(c) === s.key).length}</small></button>)}
          {!sections.length && <p className="muted">{copy.noSections}</p>}
        </aside><div className="candidate-section-content">
          {!section ? <div className="candidate-constructor-empty"><h2>{copy.startSection}</h2>{!locked && <button type="button" className="btn btn-ghost" onClick={addSection}>{copy.addSection}</button>}</div> : <>
            <div className="candidate-section-heading"><h2 ref={sectionTitle} tabIndex={-1}>{pick(section)}</h2>{isAdmin && <div className="candidate-row-actions">
              <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => startRename('section', section)}>{copy.renameSection}</button>
              {!locked && <><button type="button" className="btn btn-ghost btn-sm" title={copy.moveUp} aria-label={`${copy.moveSectionUp}: ${pick(section)}`} disabled={busy || sections[0]?.key === section.key} onClick={() => moveSection(-1)}>↑</button><button type="button" className="btn btn-ghost btn-sm" title={copy.moveDown} aria-label={`${copy.moveSectionDown}: ${pick(section)}`} disabled={busy || sections.at(-1)?.key === section.key} onClick={() => moveSection(1)}>↓</button><button type="button" className="btn btn-ghost btn-sm candidate-danger" disabled={busy} onClick={removeSection}>{copy.deleteSection}</button></>}
            </div>}</div>
            {!locked && <div className="candidate-section-settings"><label>{copy.nameRu}<input required maxLength={200} value={section.name_ru} disabled={busy} onChange={e => changeSection('name_ru', e.target.value)} /></label><label>{copy.nameKk}<input required maxLength={200} value={section.name_kk} disabled={busy} onChange={e => changeSection('name_kk', e.target.value)} /></label><label>{copy.sectionType}<select value={section.kind} disabled={busy} onChange={e => changeSection('kind', e.target.value)}>{['general', 'technical', 'psychological'].map(kind => <option key={kind} value={kind}>{copy[`section_${kind}`]}</option>)}</select></label></div>}
            <div className="candidate-indicator-list">{criteria.map((c, index) => <div key={c.position} className={`candidate-indicator ${!c.enabled ? 'is-disabled' : ''}`}>
              <div className="candidate-indicator-line"><span className="candidate-order">{index + 1}</span><button ref={expanded === c.position ? criterionTitle : null} className="candidate-indicator-name" type="button" aria-expanded={expanded === c.position} onClick={() => setExpanded(old => old === c.position ? null : c.position)}><strong>{pick(c)}</strong><small>{hasDossierSource(c) ? sourceLabel(sourceDefinition(c.source, sources) || c.source, lang) || copy.fromDossier : copy.manual}</small></button><span className="candidate-indicator-points">{formatPoints(c.max_points, lang)} <small>{copy.points}</small></span>
                {isAdmin && <button type="button" className="btn btn-ghost btn-sm candidate-rename-button" disabled={busy} aria-label={`${copy.renameCriterion}: ${pick(c)}`} onClick={() => startRename('criterion', c)}>{copy.rename}</button>}
                {!locked ? <><label className="candidate-checkbox"><input type="checkbox" checked={c.enabled} disabled={busy} aria-label={`${copy.enabled}: ${pick(c)}`} onChange={e => change(c.position, 'enabled', e.target.checked)} /><span>{copy.enabled}</span></label><div className="candidate-row-actions"><button type="button" className="btn btn-ghost btn-sm" aria-label={`${copy.moveUp}: ${pick(c)}`} disabled={busy || index === 0} onClick={() => moveCriterion(c.position, -1)}>↑</button><button type="button" className="btn btn-ghost btn-sm" aria-label={`${copy.moveDown}: ${pick(c)}`} disabled={busy || index === criteria.length - 1} onClick={() => moveCriterion(c.position, 1)}>↓</button><button type="button" className="btn btn-ghost btn-sm candidate-danger" disabled={busy} aria-label={`${copy.deleteCriterion}: ${pick(c)}`} onClick={() => removeCriterion(c)}>{copy.remove}</button></div></> : !c.enabled && <span className="badge">{copy.excluded}</span>}
              </div>
              {expanded === c.position && <div className="candidate-indicator-detail">{!locked && <div className="candidate-section-settings"><label>{copy.nameRu}<input required maxLength={200} value={c.name_ru} disabled={busy} onChange={e => change(c.position, 'name_ru', e.target.value)} /></label><label>{copy.nameKk}<input required maxLength={200} value={c.name_kk} disabled={busy} onChange={e => change(c.position, 'name_kk', e.target.value)} /></label><label>{copy.maximum}<input type="number" min="0.01" max="10000" step="0.01" required value={c.max_points} disabled={busy} onChange={e => change(c.position, 'max_points', e.target.value)} /></label></div>}
                {!locked && <label className="candidate-transfer">{copy.section}<select value={criterionSection(c)} disabled={busy} onChange={e => transferCriterion(c, e.target.value)}>{sections.map(s => <option key={s.key} value={s.key}>{pick(s)}</option>)}</select></label>}
                {c.block !== 'psychological' ? <CandidateSourceEditor criterion={c} catalog={sources} disabled={locked || busy || !sources} onChange={source => change(c.position, 'source', source)} /> : <p className="muted">{copy.manualPsychology}</p>}
                {!locked && c.block !== 'psychological' && <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => setTab('dossierFields')}>{copy.addField}</button>}
              </div>}
            </div>)}{!criteria.length && <p className="empty">{copy.noCriteria}</p>}</div>
            {!locked && <button type="button" className="btn btn-ghost" disabled={busy || method.criteria.length >= 500} onClick={addCriterion}>{copy.addCriterion}</button>}
          </>}
        </div></div>
        {!locked && <div className="candidate-save-bar"><button type="submit" className="btn" disabled={busy || !dirty}>{busy ? copy.saving : copy.saveDraft}</button><button type="button" className="btn btn-ghost" disabled={busy || dirty || !method.criteria.some(c => c.enabled)} onClick={activate}>{copy.activate}</button><span className="muted" role="status">{dirty ? copy.unsaved : copy.draftSaved}</span></div>}
      </form>}
    </>)}
    {creating && <CreateMethodDialog onClose={() => setCreating(false)} onCreated={next => { accept(next); setCreating(false) }} />}
    {renaming && <RenameMethodItemDialog target={renaming} busy={busy} error={renameError} onClose={closeRename} onApply={applyRename} />}
  </div>
}

function RenameMethodItemDialog({ target, busy, error, onClose, onApply }) {
  const { lang } = useI18n(), copy = candidateText(lang), dialog = useRef(null)
  const [names, setNames] = useState({ name_ru: target.name_ru, name_kk: target.name_kk })
  const changed = names.name_ru !== target.name_ru || names.name_kk !== target.name_kk
  const markRenamed = useUnsavedChanges(changed, copy.discard, 'methodology-rename')
  const valid = names.name_ru.trim() && names.name_kk.trim()
    && (names.name_ru.trim() !== target.name_ru || names.name_kk.trim() !== target.name_kk)
  useEffect(() => { dialog.current.showModal() }, [])
  const close = event => { event?.preventDefault(); if (!busy && (!changed || window.confirm(copy.discard))) { markRenamed(); onClose() } }
  const submit = async event => { event.preventDefault(); if (valid && await onApply(names)) markRenamed() }
  const action = target.createVersion ? target.hasDraft ? copy.saveRename : copy.createAndRename : copy.applyRename
  return <dialog ref={dialog} className="candidate-modal candidate-rename-modal" onCancel={close} aria-labelledby="rename-method-item-title">
    <form onSubmit={submit}>
      <div className="candidate-modal-title"><h2 id="rename-method-item-title">{target.kind === 'section' ? copy.renameSection : copy.renameCriterion}</h2><button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={close}>{copy.close}</button></div>
      <p className="muted">{target.createVersion ? target.hasDraft ? copy.renameExistingDraftHint : copy.renameVersionHint : copy.renameDraftHint}</p>
      {error && <p className="alert alert-bad" role="alert">{error}</p>}
      <div className="candidate-method-names">{['ru', 'kk'].map(language => <label key={language}>{language === 'ru' ? copy.nameRu : copy.nameKk}<input autoFocus={language === lang} required maxLength={200} disabled={busy} value={names[`name_${language}`]} onChange={e => setNames(old => ({ ...old, [`name_${language}`]: e.target.value }))} /></label>)}</div>
      <div className="candidate-row-actions"><button type="submit" className="btn" disabled={busy || !valid}>{busy ? copy.saving : action}</button><button type="button" className="btn btn-ghost" disabled={busy} onClick={close}>{copy.cancel}</button></div>
    </form>
  </dialog>
}

function CreateMethodDialog({ onClose, onCreated }) {
  const { lang } = useI18n(), copy = candidateText(lang), dialog = useRef(null)
  const [names, setNames] = useState({ name_ru: '', name_kk: '' }), [busy, setBusy] = useState(false), [error, setError] = useState(null)
  const markCreated = useUnsavedChanges(Object.values(names).some(Boolean), copy.discard, 'new-methodology')
  useEffect(() => { dialog.current.showModal() }, [])
  const close = event => { event?.preventDefault(); if (!busy && (!Object.values(names).some(Boolean) || window.confirm(copy.discard))) onClose() }
  const submit = async event => { event.preventDefault(); setBusy(true); setError(null); try { const { data } = await candidateApi.create(names); markCreated(); onCreated(data) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) } }
  return <dialog ref={dialog} className="candidate-modal candidate-create-modal" onCancel={close} aria-labelledby="create-method-title"><form onSubmit={submit}><div className="candidate-modal-title"><h2 id="create-method-title">{copy.createMethod}</h2><button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={close}>{copy.close}</button></div>{error && <p className="alert alert-bad" role="alert">{error}</p>}<div className="candidate-method-names">{['ru', 'kk'].map(language => <label key={language}>{language === 'ru' ? copy.nameRu : copy.nameKk}<input autoFocus={language === 'ru'} required maxLength={200} disabled={busy} value={names[`name_${language}`]} onChange={e => setNames(old => ({ ...old, [`name_${language}`]: e.target.value }))} /></label>)}</div><button type="submit" className="btn" disabled={busy}>{busy ? copy.saving : copy.createMethod}</button></form></dialog>
}

function AssessmentMatrix({ methodologyId, refresh }) {
  const { lang, pick } = useI18n(), copy = candidateText(lang)
  const [search, setSearch] = useState(''), [query, setQuery] = useState(''), [offset, setOffset] = useState(0), [section, setSection] = useState('summary')
  const [result, setResult] = useState(null), [loading, setLoading] = useState(false), [error, setError] = useState(null), [person, setPerson] = useState(null), [reload, setReload] = useState(0)
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0) }, 250); return () => clearTimeout(timer) }, [search])
  useEffect(() => { setOffset(0); setSection('summary') }, [methodologyId])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null); setResult(null)
    candidateApi.matrix({ methodology_id: methodologyId, search: query, offset, limit: 20 }, controller.signal).then(({ data }) => { if (!controller.signal.aborted) setResult(data) }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [methodologyId, query, offset, refresh, reload])
  const sections = methodologySections(result?.methodology), criteria = section === 'summary' ? [] : orderedCriteria(result?.methodology, section === 'all' ? null : section)
  return <>
    <div className="candidate-toolbar"><div className="field" style={{ flex: '1 1 250px', margin: 0 }}><label htmlFor="candidate-matrix-search">{copy.search}</label><input id="candidate-matrix-search" value={search} onChange={e => setSearch(e.target.value)} type="search" /></div><label>{copy.criteria}<select value={section} onChange={e => setSection(e.target.value)}><option value="summary">{copy.summary}</option>{sections.map(s => <option key={s.key} value={s.key}>{pick(s)}</option>)}<option value="all">{copy.all}</option></select></label><span className="muted">{copy.found}: {result?.total ?? '—'}</span></div>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    <div className="candidate-scroll candidate-matrix" aria-busy={loading}><table><thead><tr><th className="candidate-identity">{copy.person}</th><th>{copy.unit}</th>{criteria.map(c => <th className="candidate-factor" key={c.id}>{pick(c)}<small>{c.enabled ? `${copy.maximum}: ${formatPoints(c.max_points, lang)}` : copy.excluded}</small></th>)}<th className="candidate-final">{copy.result}</th></tr></thead><tbody>{result?.items.map(row => <tr key={row.id}>
      <td className="candidate-identity"><button type="button" className="candidate-name-button" disabled={result.methodology.status === 'draft'} onClick={() => setPerson(row)} title={copy.open}>{row.full_name}</button><small>{row.personal_number || row.anonymous_code || row.id}</small></td><td>{pick(row.org_unit) || '—'}</td>
      {criteria.map(c => <td key={c.id} title={!c.enabled ? copy.excluded : c.block === 'technical' && !row.summary.technical_profile ? copy.notApplicable : row.scores[c.position] == null ? copy.noScore : ''}>{!c.enabled || (c.block === 'technical' && !row.summary.technical_profile) ? '—' : row.scores[c.position] == null ? '…' : formatPoints(row.scores[c.position], lang)}</td>)}
      <td className="candidate-final"><strong>{formatPoints(row.summary.earned_points, lang)} / {formatPoints(row.summary.max_points, lang)}</strong><span>{formatPoints(row.summary.percent, lang)}{row.summary.percent == null ? '' : '%'}</span><small>{copy.completeness}: {row.summary.filled_count}/{row.summary.applicable_count}</small>{row.summary.partial_visibility && <small>{copy.partialShort}</small>}</td>
    </tr>)}{result && !result.items.length && <tr><td colSpan={criteria.length + 3} className="empty">{copy.empty}</td></tr>}</tbody></table></div>
    <div className="candidate-pagination"><button type="button" className="btn btn-ghost btn-sm" disabled={!offset || loading} onClick={() => setOffset(x => Math.max(0, x - 20))}>{copy.previous}</button><span>{copy.page} {Math.floor(offset / 20) + 1} / {Math.max(1, Math.ceil((result?.total || 0) / 20))}</span><button type="button" className="btn btn-ghost btn-sm" disabled={loading || offset + 20 >= (result?.total || 0)} onClick={() => setOffset(x => x + 20)}>{copy.next}</button></div>
    {person && <EvaluationDialog person={person} methodologyId={methodologyId} onClose={() => setPerson(null)} onChanged={() => setReload(x => x + 1)} />}
  </>
}

function EvaluationDialog({ person, methodologyId, onClose, onChanged }) {
  const { lang } = useI18n(), copy = candidateText(lang), dialog = useRef(null)
  useEffect(() => { dialog.current.showModal() }, [])
  const close = event => runAfterUnsavedConfirmation(onClose, { event, scope: CANDIDATE_SCOPE })
  return <dialog ref={dialog} className="candidate-modal" onCancel={close} aria-labelledby="candidate-modal-title"><div className="candidate-modal-title"><h2 id="candidate-modal-title">{person.full_name}</h2><button type="button" className="btn btn-ghost btn-sm" onClick={close}>{copy.close}</button></div><CandidateEvaluation employeeId={person.id} initialMethodologyId={methodologyId} onChanged={onChanged} /></dialog>
}
