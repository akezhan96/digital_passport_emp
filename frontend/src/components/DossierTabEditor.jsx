import React, { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api'
import { useI18n } from '../i18n'
import { dossierSubsectionText } from '../i18n/dossierSubsections'
import { dossierSubsectionsApi as api } from '../dossierSubsectionsApi'
import { confirmUnsavedLeave, CANDIDATE_SCOPE } from '../unsavedChanges'
import { useFormChanges } from '../useFormChanges'

const scope = `${CANDIDATE_SCOPE}:dossier-tab-editor`
export const fieldTypes = ['text', 'date', 'number', 'boolean']

function initialForm(kind, row, fields) {
  if (kind === 'tab') return { name_ru: row?.name_ru || '', name_kk: row?.name_kk || '', visibility: row?.visibility || 'public' }
  if (kind === 'field') return { name_ru: row?.name_ru || '', name_kk: row?.name_kk || '', field_type: row?.field_type || 'text' }
  return { title: row?.title || '', description: row?.description || '',
    values: Object.fromEntries(fields.map(field => [field.id, String(row?.values?.[field.id] ?? '')])) }
}

function typedValue(type, raw) {
  if (raw === '') return null
  if (type === 'boolean') return raw === 'true'
  if (type === 'number') return Number(raw)
  return raw.trim() || null
}

function ValueInput({ field, value, onChange, focus, copy, pick }) {
  return <label>{pick(field)}
    {field.field_type === 'boolean' ? <select value={value} onChange={onChange} autoFocus={focus}>
      <option value="">{copy.emptyValue}</option><option value="true">{copy.yes}</option><option value="false">{copy.no}</option>
    </select> : <input autoFocus={focus} type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
      maxLength={field.field_type === 'text' ? 4000 : undefined} step={field.field_type === 'number' ? '0.0001' : undefined}
      value={value} onChange={onChange} />}
  </label>
}

export default function DossierTabEditor({ kind, row, sectionId, fields = [], employeeId, onClose, onSaved }) {
  const { lang, pick } = useI18n()
  const copy = dossierSubsectionText(lang)
  const dialog = useRef(null)
  const active = fields.filter(field => field.is_active)
  const [form, setForm] = useState(() => initialForm(kind, row, active))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const accept = useFormChanges(form, { scope })
  useEffect(() => { const node = dialog.current; node.showModal(); return () => node.close() }, [])
  function close(event, reload = false) {
    event?.preventDefault()
    if (!busy && confirmUnsavedLeave(scope)) onClose(reload)
  }
  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))
  const updateValue = (id, value) => setForm(prev => ({ ...prev, values: { ...prev.values, [id]: value } }))
  const valid = kind === 'entry'
    ? Boolean(form.title.trim() || active.some(field => typedValue(field.field_type, form.values[field.id] ?? '') !== null))
    : Boolean(form.name_ru.trim() && form.name_kk.trim())
  async function submit(event) {
    event.preventDefault()
    if (!valid || busy) return
    setBusy(true); setError(null)
    try {
      let response
      if (kind === 'entry') {
        const body = { title: form.title.trim(), description: form.description.trim(), values: {} }
        for (const field of active) {
          const value = typedValue(field.field_type, form.values[field.id] ?? '')
          if (value !== (row?.values?.[field.id] ?? null)) body.values[field.id] = value
        }
        response = row ? await api.editEntry(employeeId, sectionId, row.id, { ...body, expected_revision: row.revision })
          : await api.createEntry(employeeId, sectionId, body)
      } else {
        const body = { ...form, name_ru: form.name_ru.trim(), name_kk: form.name_kk.trim() }
        if (row) body.expected_revision = row.revision
        if (kind === 'tab') response = row ? await api.editTab(row.id, body) : await api.createTab(body)
        else response = row ? await api.editField(sectionId, row.id, body) : await api.createField(sectionId, body)
      }
      accept()
      onSaved(response.data)
    } catch (failure) { setError(failure) } finally { setBusy(false) }
  }
  const heading = kind === 'tab' ? (row ? copy.editTab : copy.newTab)
    : kind === 'field' ? (row ? copy.editField : copy.newField) : (row ? copy.editEntry : copy.addEntry)
  const notes = <>
    <label>{copy.title}<input autoFocus={!active.length} maxLength={200} required={!active.length}
      value={form.title} onChange={e => update('title', e.target.value)} /></label>
    <label>{copy.description}<textarea rows={3} maxLength={4000} value={form.description}
      onChange={e => update('description', e.target.value)} /></label>
  </>
  return <dialog ref={dialog} className="dossier-subsection-dialog" onCancel={close} aria-labelledby="dossier-editor-title"><form onSubmit={submit}>
    <div className="dossier-editor-heading"><h3 id="dossier-editor-title">{heading}</h3>
      <button type="button" className="btn btn-ghost btn-sm" aria-label={copy.close} disabled={busy} onClick={close}>×</button></div>
    <fieldset className="dossier-editor-fields" disabled={busy}>
      {kind === 'entry' ? <>
        {active.map((field, i) => <ValueInput key={field.id} field={field} focus={i === 0} copy={copy} pick={pick}
          value={form.values[field.id] ?? ''} onChange={e => updateValue(field.id, e.target.value)} />)}
        {active.length ? <details open={Boolean(row?.title || row?.description)} className="dossier-extra-notes">
          <summary>{copy.notes}</summary><div>{notes}</div></details> : notes}
      </> : <>
        {kind === 'tab' && <p className="muted">{copy.shared}</p>}
        <label>{copy.nameRu}<input autoFocus required maxLength={120} value={form.name_ru} onChange={e => update('name_ru', e.target.value)} /></label>
        <label>{copy.nameKk}<input required maxLength={120} value={form.name_kk} onChange={e => update('name_kk', e.target.value)} /></label>
        {kind === 'field' ? <label>{copy.fieldType}<select value={form.field_type} onChange={e => update('field_type', e.target.value)}>
          {fieldTypes.map(type => <option key={type} value={type}>{copy[type]}</option>)}</select></label>
          : row?.tab === 'history' ? <p className="muted">{copy.historyPrivate}</p> : <label>{copy.access}
            <select value={form.visibility} onChange={e => update('visibility', e.target.value)}>
              <option value="public">{copy.public}</option><option value="admin">{copy.private}</option></select></label>}
      </>}
    </fieldset>
    {error && <div className="alert alert-bad" role="alert">{errorMessage(error)}{' '}
      {[404,409].includes(error.response?.status) && <button type="button" className="btn btn-sm btn-ghost"
        onClick={event => close(event, true)}>{copy.reload}</button>}</div>}
    <div className="btn-row dossier-editor-actions"><button type="button" className="btn btn-ghost" disabled={busy} onClick={close}>{copy.cancel}</button>
      <button type="submit" className="btn" disabled={busy || !valid}>{busy ? copy.saving : copy.save}</button></div>
  </form></dialog>
}
