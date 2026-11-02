import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

const BLANK = { code: '', name_ru: '', name_kk: '', name_en: '', description: '' }

/**
 * Creating catalogues the schema never anticipated. Built-in catalogues are
 * real tables with real foreign keys and cannot be invented at runtime; these
 * are stored generically and served through the same endpoints, so the editor
 * on the Catalogues tab treats them identically.
 */
export default function CustomCatalogAdmin({ onCreated }) {
  const { t, pick } = useI18n()
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState(BLANK)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(true)

  const load = useCallback(() => {
    setBusy(true)
    api.customCatalogs()
      .then((r) => setRows(r.data.data))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setBusy(false))
  }, [])

  useEffect(() => { load() }, [load])

  const submit = async (ev) => {
    ev.preventDefault()
    setError(null)
    setNotice(null)
    try {
      await api.customCatalogCreate(draft)
      setDraft(BLANK)
      setNotice(t('common.saved'))
      load()
      onCreated?.()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const remove = async (row) => {
    if (!window.confirm(t('customCatalog.deleteWarn'))) return
    setError(null)
    try {
      await api.customCatalogDelete(row.id)
      load()
      onCreated?.()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <>
      <p className="page-hint">{t('customCatalog.hint')}</p>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="card">
        <h3>{t('customCatalog.add')}</h3>
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="field">
              <label>{t('customCatalog.code')}</label>
              <input value={draft.code} required
                     placeholder="AWARDS"
                     onChange={(e) => setDraft({ ...draft,
                       code: e.target.value.toUpperCase() })} />
            </div>
            <div className="field">
              <label>{t('catalogs.nameRu')}</label>
              <input value={draft.name_ru} required
                     onChange={(e) => setDraft({ ...draft,
                       name_ru: e.target.value })} />
            </div>
          </div>
          <div className="form-row">
            <div className="field">
              <label>{t('catalogs.nameKk')}</label>
              <input value={draft.name_kk}
                     onChange={(e) => setDraft({ ...draft,
                       name_kk: e.target.value })} />
            </div>
          </div>
          <div className="field">
            <label>{t('customCatalog.description')}</label>
            <input value={draft.description}
                   onChange={(e) => setDraft({ ...draft,
                     description: e.target.value })} />
          </div>
          <button className="btn" type="submit">{t('common.add')}</button>
        </form>
      </div>

      {busy ? <div className="spinner" /> : (
        <div className="card flush">
          <table>
            <thead><tr>
              <th>{t('customCatalog.code')}</th>
              <th>{t('customCatalog.name')}</th>
              <th>{t('customCatalog.description')}</th>
              <th className="num">{t('customCatalog.items')}</th>
              <th style={{ width: 110 }} />
            </tr></thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={5} className="empty">{t('common.none')}</td></tr>
              )}
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="mono">{row.code}</td>
                  <td><strong>{pick(row)}</strong></td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {row.description || '—'}
                  </td>
                  <td className="num">{row.item_count}</td>
                  <td>
                    <button className="btn btn-danger btn-sm"
                            onClick={() => remove(row)}>
                      {t('common.delete')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
