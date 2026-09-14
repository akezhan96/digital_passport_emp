import React, { useEffect, useState, useCallback, useRef } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Documents attached to one profile section: passport photo on the general
 * tab, diploma scan on education, language certificate on languages, and so on.
 */
export default function Attachments({ entityType, entityId, compact = false,
                                      onError, readOnly = false }) {
  const { t } = useI18n()
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [description, setDescription] = useState('')
  const inputRef = useRef(null)

  const load = useCallback(() => {
    if (!entityId) return
    api.attachments(entityType, entityId)
      .then((r) => setRows(r.data.data))
      .catch((e) => onError?.(errorMessage(e)))
  }, [entityType, entityId, onError])

  useEffect(() => { load() }, [load])

  const upload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    onError?.(null)
    setBusy(true)
    try {
      await api.attachmentUpload(entityType, entityId, file, description)
      setDescription('')
      if (inputRef.current) inputRef.current.value = ''
      load()
    } catch (e) {
      onError?.(errorMessage(e))
      if (inputRef.current) inputRef.current.value = ''
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm(t('files.deleteWarn'))) return
    try {
      await api.attachmentDelete(id)
      load()
    } catch (e) {
      onError?.(errorMessage(e))
    }
  }

  const example = t(`files.examples.${entityType}`)
  const hasExample = example && !example.startsWith('files.')

  return (
    <div className={compact ? '' : 'card'}>
      {!compact && <h3>{t('files.title')}</h3>}

      {!readOnly && (
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap',
                    alignItems: 'flex-end', marginBottom: rows.length ? 14 : 0 }}>
        <div className="field" style={{ flex: 1, minWidth: 200, marginBottom: 0 }}>
          <label>{t('files.description')}</label>
          <input value={description} placeholder={hasExample ? example : ''}
                 onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>{t('files.upload')}</label>
          <input ref={inputRef} type="file" disabled={busy} onChange={upload}
                 accept="application/pdf,image/jpeg,image/png" />
        </div>
      </div>
      )}
      {!readOnly && (
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 12 }}>
          {busy ? t('files.uploading') : t('files.hint')}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 12.5 }}>{t('files.none')}</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th />
              <th>{t('common.name')}</th>
              <th>{t('files.description')}</th>
              <th className="num">{t('files.size')}</th>
              <th>{t('files.uploaded')}</th>
              <th style={{ width: 150 }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id}>
                <td style={{ width: 52 }}>
                  {a.is_image ? (
                    <img src={api.attachmentUrl(a.id)} alt=""
                         style={{ width: 40, height: 40, objectFit: 'cover',
                                  borderRadius: 4, border: '1px solid var(--slate-200)' }} />
                  ) : (
                    <span style={{ fontSize: 20 }}>📄</span>
                  )}
                </td>
                <td>{a.original_name}</td>
                <td className="muted">{a.description || '—'}</td>
                <td className="num muted">{humanSize(a.size_bytes)}</td>
                <td className="muted mono" style={{ fontSize: 11.5 }}>
                  {a.uploaded_at ? a.uploaded_at.slice(0, 10) : ''}
                </td>
                <td>
                  <div className="btn-row">
                    <a className="btn btn-ghost btn-sm" href={api.attachmentUrl(a.id)}
                       target="_blank" rel="noreferrer">{t('files.open')}</a>
                    {!readOnly && (
                      <button className="btn btn-danger btn-sm"
                              onClick={() => remove(a.id)}>×</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
