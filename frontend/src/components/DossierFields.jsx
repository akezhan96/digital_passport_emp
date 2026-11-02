import React, { useEffect, useState } from 'react'
import { candidateApi } from '../candidateApi'
import { errorMessage } from '../api'
import { useI18n } from '../i18n'
import { candidateText } from '../i18n/candidateMethodology'
import { optionValue, sourceLabel } from '../candidateSources'
import { useUnsavedChanges } from '../useUnsavedChanges'
import { CANDIDATE_SCOPE, METHODOLOGY_SCOPE } from '../unsavedChanges'

const optionRow = option => typeof option === 'object' ? { ...option, name_ru: option.name_ru || option.label || String(option.value), name_kk: option.name_kk || option.label || String(option.value) }
  : { value: option, name_ru: String(option), name_kk: String(option) }
const blankOption = () => ({ value: `option_${globalThis.crypto.randomUUID().slice(0, 8)}`, name_ru: '', name_kk: '' })
const blankField = () => ({ name_ru: '', name_kk: '', field_type: 'boolean', visibility: 'public', is_required: false, options: [] })

export function DossierFieldManager({ onChanged }) {
  const { lang } = useI18n()
  const copy = candidateText(lang)
  const [rows, setRows] = useState(null)
  const [draft, setDraft] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [refresh, setRefresh] = useState(0)
  const markSaved = useUnsavedChanges(dirty, copy.discard, `${METHODOLOGY_SCOPE}:fields`)
  useEffect(() => {
    const controller = new AbortController()
    candidateApi.fields(controller.signal).then(({ data }) => { if (!controller.signal.aborted) setRows(data.data) })
      .catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
    return () => controller.abort()
  }, [refresh])
  const edit = field => {
    if (dirty && !window.confirm(copy.discard)) return
    markSaved(); setDirty(false); setError(null)
    setDraft(field ? { ...field, options: (field.options || []).map(optionRow) } : blankField())
  }
  const change = (key, value) => { setDraft(old => ({ ...old, [key]: value })); setDirty(true) }
  const save = async event => {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const body = { name_ru: draft.name_ru.trim(), name_kk: draft.name_kk.trim(), visibility: draft.visibility || 'public',
        is_required: draft.is_required, options: draft.field_type === 'select' ? draft.options : [] }
      if (draft.id) await candidateApi.updateField(draft.id, body)
      else await candidateApi.createField({ ...body, field_type: draft.field_type })
      markSaved(); setDirty(false); setDraft(null); setRefresh(x => x + 1); onChanged?.()
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const setActive = async field => {
    setBusy(true); setError(null)
    try { await candidateApi.updateField(field.id, { is_active: !field.is_active }); setRefresh(x => x + 1); onChanged?.() }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const remove = async field => {
    if (!window.confirm(`${copy.deleteFieldConfirm}\n«${sourceLabel(field, lang)}»\n\n${copy.deleteFieldValuesWarning}`)) return
    setBusy(true); setError(null)
    try { await candidateApi.removeField(field.id); setRefresh(x => x + 1); onChanged?.() }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const filtered = rows?.filter(field => `${field.name_ru} ${field.name_kk}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  return <div className="candidate-dossier-manager">
    <div className="candidate-toolbar"><input type="search" aria-label={copy.findField} placeholder={copy.findField} value={search} onChange={e => setSearch(e.target.value)} />
      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => edit(null)}>{copy.addField}</button></div>
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    {draft && <form className="candidate-field-editor" onSubmit={save}>
      <fieldset disabled={busy}><legend>{draft.id ? copy.editField : copy.addField}</legend>
        <div className="candidate-method-names">{['ru', 'kk'].map(language => <label key={language}>{language === 'ru' ? copy.nameRu : copy.nameKk}
          <input required maxLength={200} value={draft[`name_${language}`]} onChange={e => change(`name_${language}`, e.target.value)} /></label>)}</div>
        <div className="candidate-source-selects"><label>{copy.fieldType}<select value={draft.field_type} disabled={Boolean(draft.id)} onChange={e => {
          change('field_type', e.target.value)
          if (e.target.value === 'select' && !draft.options.length) change('options', [blankOption()])
        }}>{['boolean', 'number', 'select', ...(draft.id && !['boolean', 'number', 'select'].includes(draft.field_type) ? [draft.field_type] : [])].map(kind => <option key={kind} value={kind}>{copy[`type_${kind}`] || kind}</option>)}</select></label>
          <label title={draft.id ? copy.visibilityAtCreation : undefined}>{copy.visibility}<select value={draft.visibility || 'public'} disabled={Boolean(draft.id)} onChange={e => change('visibility', e.target.value)}><option value="public">{copy.publicField}</option><option value="admin">{copy.privateField}</option></select></label>
          <label className="candidate-checkbox"><input type="checkbox" checked={draft.is_required} onChange={e => change('is_required', e.target.checked)} />{copy.requiredField}</label>
        </div>
        {draft.field_type === 'select' && <div className="candidate-option-list">{draft.options.map((option, index) => <div className="candidate-option-row" key={option.value}>
          {['ru', 'kk'].map(language => <label key={language}>{language === 'ru' ? copy.optionRu : copy.optionKk}<input required maxLength={200} value={option[`name_${language}`]} onChange={e => change('options', draft.options.map((o, at) => at === index ? { ...o, [`name_${language}`]: e.target.value } : o))} /></label>)}
          <button type="button" className="btn btn-ghost btn-sm" disabled={draft.options.length <= 1} aria-label={`${copy.remove} ${index + 1}`} onClick={() => change('options', draft.options.filter((_, at) => at !== index))}>{copy.remove}</button>
        </div>)}<button type="button" className="btn btn-ghost btn-sm" disabled={draft.options.length >= 100} onClick={() => change('options', [...draft.options, blankOption()])}>{copy.addOption}</button></div>}
        <div className="candidate-toolbar"><button className="btn" type="submit" disabled={busy || !dirty}>{busy ? copy.saving : copy.save}</button>
          <button className="btn btn-ghost" type="button" onClick={() => { if (!dirty || window.confirm(copy.discard)) { markSaved(); setDraft(null); setDirty(false) } }}>{copy.cancel}</button></div>
      </fieldset>
    </form>}
    {!rows ? <div className="spinner" /> : <div className="candidate-scroll"><table><thead><tr><th>{copy.fieldName}</th><th>{copy.fieldType}</th><th>{copy.visibility}</th><th>{copy.actions}</th></tr></thead><tbody>
      {filtered.map(field => <tr key={field.id}><td>{sourceLabel(field, lang)}{!field.is_active && <span className="badge">{copy.excluded}</span>}</td><td>{copy[`type_${field.field_type}`] || field.field_type}</td><td>{field.visibility === 'admin' ? copy.privateField : copy.publicField}</td>
        <td><div className="candidate-row-actions"><button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => edit(field)}>{copy.edit}</button><button type="button" className="btn btn-ghost btn-sm" disabled={busy || draft?.id === field.id} onClick={() => setActive(field)}>{field.is_active ? copy.disableField : copy.enableField}</button><button type="button" className="btn btn-ghost btn-sm candidate-danger" disabled={busy || draft?.id === field.id} onClick={() => remove(field)}>{copy.deleteField}</button></div></td></tr>)}
      {!filtered.length && <tr><td colSpan={4} className="empty">{copy.noFields}</td></tr>}
    </tbody></table></div>}
  </div>
}

export function DossierFieldValues({ employeeId, readOnly, onSaved, onDirtyChange }) {
  const { lang } = useI18n()
  const copy = candidateText(lang)
  const [fields, setFields] = useState(null)
  const [values, setValues] = useState({})
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const markSaved = useUnsavedChanges(dirty, copy.discard, CANDIDATE_SCOPE)
  useEffect(() => {
    const controller = new AbortController(); setFields(null); setError(null)
    candidateApi.fieldValues(employeeId, controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) { setFields(data.data); setValues(Object.fromEntries(data.data.map(field => [field.definition_id, field.value ?? '']))); setDirty(false) }
    }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
    return () => controller.abort()
  }, [employeeId])
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false) }, [dirty, onDirtyChange])
  const change = (id, value) => { setValues(old => ({ ...old, [id]: value })); setDirty(true); setSaved(false) }
  const save = async event => {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const { data } = await candidateApi.saveFieldValues(employeeId, values)
      setFields(data.data); setValues(Object.fromEntries(data.data.map(field => [field.definition_id, field.value ?? ''])))
      markSaved(); setDirty(false); setSaved(true); onSaved?.()
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  return <div className="candidate-field-values">
    {error && <p className="alert alert-bad" role="alert">{error}</p>}
    {!fields ? !error && <div className="spinner" /> : !fields.length ? <p className="muted">{copy.noFields}</p> : <form onSubmit={save}>
      <fieldset disabled={readOnly || busy}><legend className="sr-only">{copy.dossierFields}</legend><div className="candidate-field-grid">
        {fields.map(field => <label key={field.definition_id}>{sourceLabel(field, lang)}{field.is_required ? ' *' : ''}{field.visibility === 'admin' && <small>{copy.privateField}</small>}
          {field.field_type === 'boolean' ? <select value={values[field.definition_id] === '' ? '' : String(values[field.definition_id])} required={field.is_required} onChange={e => change(field.definition_id, e.target.value === '' ? '' : e.target.value === 'true')}>
            <option value="">{copy.notFilled}</option><option value="true">{copy.yes}</option><option value="false">{copy.no}</option></select>
            : field.field_type === 'select' ? <select required={field.is_required} value={values[field.definition_id]} onChange={e => change(field.definition_id, e.target.value)}><option value="">{copy.notFilled}</option>{(field.options || []).map(option => <option key={optionValue(option)} value={optionValue(option)}>{sourceLabel(option, lang)}</option>)}</select>
              : field.field_type === 'textarea' ? <textarea rows={2} required={field.is_required} value={values[field.definition_id]} onChange={e => change(field.definition_id, e.target.value)} />
                : <input type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'} step={field.field_type === 'number' ? 'any' : undefined} required={field.is_required} value={values[field.definition_id]} onChange={e => change(field.definition_id, e.target.value)} />}
        </label>)}
      </div></fieldset>
      {!readOnly && <div className="candidate-toolbar"><button type="submit" className="btn btn-ghost" disabled={!dirty || busy}>{busy ? copy.saving : copy.saveDossierFields}</button>{saved && <span className="muted" role="status">{copy.fieldsSaved}</span>}</div>}
    </form>}
  </div>
}
