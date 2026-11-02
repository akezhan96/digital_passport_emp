import React, { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import CustomFieldAdmin from '../components/CustomFieldAdmin'
import CustomCatalogAdmin from '../components/CustomCatalogAdmin'

const BLANK = { code: '', name_ru: '', name_kk: '', name_en: '' }

export default function CatalogsPage() {
  const { t, pick } = useI18n()
  const { isAdmin } = useAuth()
  const [tab, setTab] = useState('catalogs')
  // Bumped when a catalogue is created or removed, so the editor refetches.
  const [reloadKey, setReloadKey] = useState(0)

  return (
    <>
      <h2>{t('catalogs.title')}</h2>

      <div className="tabs">
        <button className={`tab ${tab === 'catalogs' ? 'active' : ''}`}
                onClick={() => setTab('catalogs')}>
          {t('catalogs.title')}
        </button>
        {isAdmin && (
          <>
            <button className={`tab ${tab === 'own' ? 'active' : ''}`}
                    onClick={() => setTab('own')}>
              {t('customCatalog.manage')}
            </button>
            <button className={`tab ${tab === 'custom' ? 'active' : ''}`}
                    onClick={() => setTab('custom')}>
              {t('extra.manage')}
            </button>
          </>
        )}
      </div>

      {(tab === 'catalogs' || !isAdmin) && (
        <CatalogEditor t={t} pick={pick} isAdmin={isAdmin} key={reloadKey} />
      )}
      {isAdmin && tab === 'own' && (
        <CustomCatalogAdmin onCreated={() => setReloadKey((n) => n + 1)} />
      )}
      {isAdmin && tab === 'custom' && <CustomFieldAdmin />}
    </>
  )
}

function CatalogEditor({ t, pick, isAdmin }) {
  const [catalogs, setCatalogs] = useState([])
  const [active, setActive] = useState('competencies')
  const [rows, setRows] = useState([])
  const [extraFields, setExtraFields] = useState([])
  const [draft, setDraft] = useState(BLANK)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    api.catalogs()
      .then((r) => setCatalogs(r.data.catalogs))
      .catch((e) => setError(errorMessage(e)))
  }, [])

  useEffect(() => {
    if (!active) return
    setBusy(true)
    setError(null)
    api.refList(active)
      .then((r) => setRows(r.data.data))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setBusy(false))

    const meta = catalogs.find((c) => c.name === active)
    setExtraFields(meta ? meta.extra_fields : [])
    setDraft(BLANK)
    setEditingId(null)
    setFilter('')
  }, [active, catalogs])

  const reload = () => api.refList(active).then((r) => setRows(r.data.data))

  const submit = async (ev) => {
    ev.preventDefault()
    setError(null)
    setNotice(null)
    try {
      if (editingId) await api.refUpdate(active, editingId, draft)
      else await api.refCreate(active, draft)
      await reload()
      setDraft(BLANK)
      setEditingId(null)
      setNotice(t('common.saved'))
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const remove = async (id) => {
    if (!window.confirm(t('common.confirmDelete'))) return
    setError(null)
    try {
      await api.refDelete(active, id)
      await reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const activeMeta = catalogs.find((c) => c.name === active)
  const visible = filter
    ? rows.filter((r) =>
        `${r.code} ${r.name_ru} ${r.name_kk} ${r.name_en}`
          .toLowerCase().includes(filter.toLowerCase()))
    : rows

  return (
    <>
      <p className="page-hint">
        {isAdmin ? t('catalogs.hint') : t('catalogs.hintViewer')}
      </p>

      {error && <div className="alert alert-bad">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      <div className="split">
        <div className="card flush">
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--slate-200)' }}>
            <strong style={{ fontSize: 13 }}>{t('catalogs.selectCatalog')}</strong>
          </div>
          <div className="list">
            {catalogs.map((c) => (
              <div key={c.name}
                   className={`list-row ${active === c.name ? 'active' : ''}`}
                   onClick={() => setActive(c.name)}>
                <div>
                  <div className="list-title">{pick(c)}</div>
                  <div className="list-sub mono" style={{ fontSize: 11 }}>
                    {c.name}
                    {c.is_custom && (
                      <span className="badge badge-conf"
                            style={{ marginLeft: 6 }}>
                        {t('customCatalog.custom')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          {isAdmin && (
          <div className="card">
            <h3>
              {editingId ? t('common.edit') : t('catalogs.addItem')}
              {activeMeta ? ` — ${pick(activeMeta)}` : ''}
            </h3>
            <form onSubmit={submit}>
              <div className="form-row">
                <div className="field">
                  <label>{t('common.code')}</label>
                  <input value={draft.code || ''}
                         onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                         required />
                </div>
                <div className="field">
                  <label>{t('catalogs.nameRu')}</label>
                  <input value={draft.name_ru || ''}
                         onChange={(e) => setDraft({ ...draft, name_ru: e.target.value })}
                         required />
                </div>
              </div>
              <div className="form-row">
                <div className="field">
                  <label>{t('catalogs.nameKk')}</label>
                  <input value={draft.name_kk || ''}
                         onChange={(e) => setDraft({ ...draft, name_kk: e.target.value })} />
                </div>
              </div>

              {extraFields.length > 0 && (
                <div className="form-row-3">
                  {extraFields.map((f) => (
                    <div className="field" key={f.field}>
                      <label>{pick(f)}</label>
                      <input
                        value={draft[f.field] ?? ''}
                        onChange={(e) => {
                          const raw = e.target.value
                          const numeric = raw !== '' && !Number.isNaN(Number(raw))
                          setDraft({ ...draft, [f.field]: numeric ? Number(raw) : raw })
                        }} />
                    </div>
                  ))}
                </div>
              )}

              <div className="btn-row">
                <button className="btn" type="submit">{t('common.save')}</button>
                {editingId && (
                  <button type="button" className="btn btn-ghost"
                          onClick={() => { setEditingId(null); setDraft(BLANK) }}>
                    {t('common.cancel')}
                  </button>
                )}
              </div>
            </form>
          </div>
          )}

          <div className="card flush">
            <div style={{ padding: '10px 14px',
                          borderBottom: '1px solid var(--slate-200)',
                          display: 'flex', gap: 12, alignItems: 'center' }}>
              <input placeholder={t('common.search')} value={filter}
                     onChange={(e) => setFilter(e.target.value)}
                     style={{ maxWidth: 280 }} />
              <span className="muted" style={{ fontSize: 12.5 }}>
                {t('common.total')}: {visible.length}
              </span>
            </div>

            {busy ? <div className="spinner" /> : (
              <div className="scroll-y" style={{ maxHeight: 620 }}>
                <table>
                  <thead>
                    <tr>
                      <th>{t('common.code')}</th>
                      <th>{t('common.name')}</th>
                      {extraFields.map((f) => <th key={f.field}>{pick(f)}</th>)}
                      {isAdmin && (
                        <th style={{ width: 130 }}>{t('common.actions')}</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {visible.length === 0 && (
                      <tr>
                        <td colSpan={(isAdmin ? 3 : 2) + extraFields.length} className="empty">
                          {t('common.none')}
                        </td>
                      </tr>
                    )}
                    {visible.map((row) => (
                      <tr key={row.id}>
                        <td className="mono">{row.code}</td>
                        <td>{pick(row)}</td>
                        {extraFields.map((f) => (
                          <td key={f.field} className="muted">
                            {String(row[f.field] ?? '')}
                          </td>
                        ))}
                        {isAdmin && (
                          <td>
                            <div className="btn-row">
                              <button className="btn btn-ghost btn-sm"
                                      onClick={() => {
                                        setEditingId(row.id)
                                        setDraft({ ...row })
                                        setNotice(null)
                                      }}>
                                {t('common.edit')}
                              </button>
                              <button className="btn btn-danger btn-sm"
                                      onClick={() => remove(row.id)}>
                                {t('common.delete')}
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
