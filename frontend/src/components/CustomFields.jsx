import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useFormChanges } from '../useFormChanges'
import { CANDIDATE_SCOPE } from '../unsavedChanges'
import { customOptionValue, customOptionLabel, displayCustomFieldValue } from '../customFieldValues'

/**
 * Renders the administrator-defined extra fields for one record and saves
 * them. The set of fields is data, so this component never hard-codes any.
 */
export default function CustomFields({ entityType, entityId, onError,
                                      readOnly = false }) {
  const { t, pick, lang } = useI18n()
  const [fields, setFields] = useState([])
  const [draft, setDraft] = useState({})
  const [loading, setLoading] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)
  const markSaved = useFormChanges(draft, { enabled: !readOnly && !loading, scope: `${CANDIDATE_SCOPE}:custom-${entityType}-${entityId}` })

  const load = useCallback(() => {
    if (!entityId) return
    setLoading(true)
    api.customValues(entityType, entityId)
      .then((r) => {
        setFields(r.data.data)
        const values = Object.fromEntries(r.data.data.map(f => [f.definition_id, f.value ?? '']))
        markSaved(values); setDraft(values)
        setDirty(false)
      })
      .catch((e) => onError?.(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [entityType, entityId, onError])

  useEffect(() => { load() }, [load])

  const save = async () => {
    onError?.(null)
    try {
      const r = await api.customValuesSave(entityType, entityId, draft)
      setFields(r.data.data)
      markSaved()
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      onError?.(errorMessage(e))
    }
  }

  const set = (id, value) => {
    setDraft((d) => ({ ...d, [id]: value }))
    setDirty(true)
  }

  if (loading) return <div className="spinner" />

  if (fields.length === 0) {
    return (
      <div className="card">
        <h3>{t('extra.title')}</h3>
        <div className="empty">{t('extra.none')}</div>
        <div className="muted" style={{ fontSize: 12 }}>{t('extra.hint')}</div>
      </div>
    )
  }

  return (
    <div className="card">
      <h3>{t('extra.title')}</h3>
      <div className="form-row">
        {fields.map((f) => (
          <div className="field" key={f.definition_id}>
            <label>
              {pick(f)}
              {f.is_required && <span style={{ color: 'var(--bad)' }}> *</span>}
            </label>

            {readOnly ? (
              <div style={{ padding: '7px 0', fontSize: 13 }}>
                {displayCustomFieldValue(f, draft[f.definition_id], lang, t('common.yes'), t('common.no'))}
              </div>
            ) : f.field_type === 'textarea' ? (
              <textarea value={draft[f.definition_id] ?? ''}
                        onChange={(e) => set(f.definition_id, e.target.value)} />
            ) : f.field_type === 'select' ? (
              <select value={draft[f.definition_id] ?? ''}
                      onChange={(e) => set(f.definition_id, e.target.value)}>
                <option value="">—</option>
                {(f.options || []).map((o, i) => {
                  const value = customOptionValue(o)
                  const label = customOptionLabel(o, lang)
                  return <option key={i} value={value}>{label}</option>
                })}
              </select>
            ) : f.field_type === 'boolean' ? (
              <select value={draft[f.definition_id] === '' || draft[f.definition_id] == null ? '' : String(draft[f.definition_id])}
                      onChange={(e) => set(f.definition_id, e.target.value === '' ? '' : e.target.value === 'true')}>
                <option value="">—</option>
                <option value="true">{t('common.yes')}</option>
                <option value="false">{t('common.no')}</option>
              </select>
            ) : (
              <input
                type={f.field_type === 'number' ? 'number'
                  : f.field_type === 'date' ? 'date' : 'text'}
                step={f.field_type === 'number' ? 'any' : undefined}
                value={draft[f.definition_id] ?? ''}
                onChange={(e) => set(f.definition_id, e.target.value)} />
            )}

            {f.help_text && (
              <div className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>
                {f.help_text}
              </div>
            )}
          </div>
        ))}
      </div>

      {!readOnly && (
        <div className="btn-row">
          <button className="btn" onClick={save} disabled={!dirty}>
            {t('common.save')}
          </button>
          {saved && <span className="badge badge-ok">{t('common.saved')}</span>}
        </div>
      )}
    </div>
  )
}
