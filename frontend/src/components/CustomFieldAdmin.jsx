import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

const ENTITIES = ['employee', 'education', 'language', 'training',
                  'work_experience', 'assessment']
const TYPES = ['text', 'textarea', 'number', 'date', 'boolean', 'select']

const BLANK = {
  entity_type: 'employee', name_ru: '', name_kk: '', name_en: '',
  field_type: 'text', options: '', help_text: '', is_required: false,
}

/** Lets an HR administrator define the extra fields shown on profile cards. */
export default function CustomFieldAdmin() {
  const { t, pick } = useI18n()
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState(BLANK)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(true)

  const load = useCallback(() => {
    setBusy(true)
    api.customFields()
      .then((r) => setRows(r.data.data))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setBusy(false))
  }, [])

  useEffect(() => { load() }, [load])

  const submit = async (ev) => {
    ev.preventDefault()
    setError(null)
    setNotice(null)
    const body = {
      ...draft,
      options: draft.field_type === 'select'
        ? draft.options.split('\n').map((o) => o.trim()).filter(Boolean)
        : [],
    }
    try {
      await api.customFieldCreate(body)
      setDraft({ ...BLANK, entity_type: draft.entity_type })
      setNotice(t('common.saved'))
      load()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const remove = async (id) => {
    if (!window.confirm(t('extra.deleteWarn'))) return
    try {
      await api.customFieldDelete(id)
      load()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const grouped = ENTITIES.map((entity) => ({
    entity,
    fields: rows.filter((r) => r.entity_type === entity),
  })).filter((g) => g.fields.length > 0)

  return (
    <>
      <p className="page-hint">{t('extra.manageHint')}</p>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="card">
        <h3>{t('extra.manageTitle')}</h3>
        <form onSubmit={submit}>
          <div className="form-row-3">
            <div className="field">
              <label>{t('extra.section')}</label>
              <select value={draft.entity_type}
                      onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}>
                {ENTITIES.map((x) => (
                  <option key={x} value={x}>{t(`extra.entities.${x}`)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{t('extra.fieldType')}</label>
              <select value={draft.field_type}
                      onChange={(e) => setDraft({ ...draft, field_type: e.target.value })}>
                {TYPES.map((x) => (
                  <option key={x} value={x}>{t(`extra.types.${x}`)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{t('extra.required')}</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8,
                              fontWeight: 400, marginTop: 6 }}>
                <input type="checkbox" style={{ width: 'auto' }}
                       checked={draft.is_required}
                       onChange={(e) => setDraft({ ...draft,
                         is_required: e.target.checked })} />
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {draft.is_required ? t('common.yes') : t('common.no')}
                </span>
              </label>
            </div>
          </div>

          <div className="form-row-3">
            <div className="field">
              <label>{t('extra.fieldName')} (RU)</label>
              <input value={draft.name_ru} required
                     onChange={(e) => setDraft({ ...draft, name_ru: e.target.value })} />
            </div>
            <div className="field">
              <label>{t('extra.fieldName')} (KK)</label>
              <input value={draft.name_kk}
                     onChange={(e) => setDraft({ ...draft, name_kk: e.target.value })} />
            </div>
            <div className="field">
              <label>{t('extra.fieldName')} (EN)</label>
              <input value={draft.name_en}
                     onChange={(e) => setDraft({ ...draft, name_en: e.target.value })} />
            </div>
          </div>

          {draft.field_type === 'select' && (
            <div className="field">
              <label>{t('extra.options')}</label>
              <textarea value={draft.options} rows={4}
                        onChange={(e) => setDraft({ ...draft, options: e.target.value })} />
            </div>
          )}

          <div className="field">
            <label>{t('extra.helpText')}</label>
            <input value={draft.help_text}
                   onChange={(e) => setDraft({ ...draft, help_text: e.target.value })} />
          </div>

          <button className="btn" type="submit">{t('common.add')}</button>
        </form>
      </div>

      {busy ? <div className="spinner" /> : grouped.length === 0 ? (
        <div className="card"><div className="empty">{t('extra.none')}</div></div>
      ) : grouped.map((group) => (
        <div className="card flush" key={group.entity}>
          <div style={{ padding: '11px 14px',
                        borderBottom: '1px solid var(--slate-200)',
                        fontWeight: 620, fontSize: 13 }}>
            {t(`extra.entities.${group.entity}`)}
            <span className="muted"> ({group.fields.length})</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('extra.fieldName')}</th>
                <th>{t('extra.fieldType')}</th>
                <th>{t('extra.options')}</th>
                <th>{t('extra.required')}</th>
                <th style={{ width: 100 }} />
              </tr>
            </thead>
            <tbody>
              {group.fields.map((f) => (
                <tr key={f.id}>
                  <td>
                    <strong>{pick(f)}</strong>
                    <div className="mono muted" style={{ fontSize: 11 }}>{f.code}</div>
                  </td>
                  <td className="muted">{t(`extra.types.${f.field_type}`)}</td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {(f.options || []).length
                      ? (f.options || []).map((o) =>
                          typeof o === 'object' ? o.value : o).join(', ')
                      : '—'}
                  </td>
                  <td>
                    {f.is_required
                      ? <span className="badge badge-warn">{t('common.yes')}</span>
                      : <span className="muted">{t('common.no')}</span>}
                  </td>
                  <td>
                    <button className="btn btn-danger btn-sm"
                            onClick={() => remove(f.id)}>{t('common.delete')}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  )
}
