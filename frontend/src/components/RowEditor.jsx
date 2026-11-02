import React, { useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useFormChanges } from '../useFormChanges'
import { CANDIDATE_SCOPE, confirmUnsavedLeave } from '../unsavedChanges'

/**
 * Inline correction of one education / language / training / career row.
 *
 * Only the fields that actually change are sent, and the server records the
 * old and new value of each, so the history shows what was corrected rather
 * than that "something was updated".
 */
export default function RowEditor({ section, row, fields, refData,
                                    onSaved, onCancel, onError }) {
  const { t, pick } = useI18n()
  const [draft, setDraft] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.key, row[f.key] ?? ''])))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const scope = `${CANDIDATE_SCOPE}:row-${section}:${row.id}`
  const markSaved = useFormChanges({ draft, reason }, { scope })

  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }))

  const submit = async (ev) => {
    ev.preventDefault()
    onError?.(null)
    setBusy(true)

    const body = { reason: reason || null }
    fields.forEach((f) => {
      let value = draft[f.key]
      if (value === '') value = null
      else if (f.kind === 'number' && value !== null) value = Number(value)
      else if (f.kind === 'ref' && value !== null) value = Number(value)
      body[f.key] = value
    })

    try {
      const r = await api.updateChild(section, row.id, body)
      markSaved(); onSaved?.(r.data.changed || [])
    } catch (e) {
      onError?.(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}
          style={{ background: 'var(--slate-50)', padding: '12px 14px',
                   borderRadius: 6 }}>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
        {t('edit.hint')}
      </div>

      <div className="form-row-3">
        {fields.map((f) => (
          <div className="field" key={f.key} style={{ marginBottom: 8 }}>
            <label>{f.label}</label>
            {f.kind === 'ref' ? (
              <select value={draft[f.key] ?? ''}
                      onChange={(e) => set(f.key, e.target.value)}>
                <option value="">—</option>
                {(refData[f.catalog] || []).map((o) => (
                  <option key={o.id} value={o.id}>{pick(o)}</option>
                ))}
              </select>
            ) : f.kind === 'boolean' ? (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8,
                              fontWeight: 400, marginTop: 5 }}>
                <input type="checkbox" style={{ width: 'auto' }}
                       checked={Boolean(draft[f.key])}
                       onChange={(e) => set(f.key, e.target.checked)} />
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {draft[f.key] ? t('common.yes') : t('common.no')}
                </span>
              </label>
            ) : (
              <input
                type={f.kind === 'date' ? 'date'
                  : f.kind === 'number' ? 'number' : 'text'}
                value={draft[f.key] ?? ''}
                onChange={(e) => set(f.key, e.target.value)} />
            )}
          </div>
        ))}
      </div>

      <div className="field" style={{ marginBottom: 10 }}>
        <label>{t('edit.reason')}</label>
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>

      <div className="btn-row">
        <button className="btn btn-sm" type="submit" disabled={busy}>
          {t('edit.save')}
        </button>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => { if (confirmUnsavedLeave(scope)) onCancel() }}>
          {t('edit.cancel')}
        </button>
      </div>
    </form>
  )
}
