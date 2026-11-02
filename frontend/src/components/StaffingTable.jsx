import React, { useEffect, useState, useCallback } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'

/**
 * A unit's establishment: which posts exist there, how many slots each holds,
 * and who is currently standing in them.
 *
 * Occupancy is never edited here because it is not stored -- it comes from the
 * career record. Widening or narrowing the table is an administrative act;
 * filling it is an appointment.
 */
export default function StaffingTable({ unitId, unitName, onChanged }) {
  const { t, pick, lang } = useI18n()
  const { isAdmin } = useAuth()
  const [data, setData] = useState(null)
  const [positions, setPositions] = useState([])
  const [grades, setGrades] = useState([])
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!unitId) return
    api.unitStaffing(unitId)
      .then((r) => setData(r.data))
      .catch((e) => setError(errorMessage(e)))
  }, [unitId])

  useEffect(() => {
    setData(null)
    setError(null)
    setAdding(false)
    setEditingId(null)
    load()
  }, [unitId, load])

  useEffect(() => {
    if (!isAdmin) return
    api.refList('positions').then((r) => setPositions(r.data.data)).catch(() => {})
    api.refList('position-grades').then((r) => setGrades(r.data.data)).catch(() => {})
  }, [isAdmin])

  const applied = (next) => {
    setData(next)
    setAdding(false)
    setEditingId(null)
    setError(null)
    onChanged?.()
  }

  const remove = async (line) => {
    if (!window.confirm(t('staffing.deleteWarn'))) return
    setError(null)
    try {
      await api.staffingDelete(line.id)
      load()
      onChanged?.()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const changeHeadcount = async (line, delta) => {
    const next = line.headcount + delta
    if (next < 0) return
    setBusy(true)
    setError(null)
    try {
      const r = await api.staffingUpdate(line.id, { headcount: next })
      applied(r.data)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (!data) return <div className="spinner" />

  const { totals } = data
  const used = positions.filter(
    (p) => !data.lines.some((l) => l.position_id === p.id))
  const percent = totals.established
    ? Math.round((totals.occupied / totals.established) * 100) : 0

  const label = (line) => line[`position_${lang}`] || line.position_ru

  return (
    <div className="card flush">
      <div style={{ padding: '11px 14px',
                    borderBottom: '1px solid var(--slate-200)',
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div>
          <strong style={{ fontSize: 13 }}>{t('staffing.unitTable')}</strong>
          {unitName && <span className="muted"> · {unitName}</span>}
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
            {t('staffing.established')}: <strong>{totals.established}</strong>
            {' · '}{t('staffing.occupied')}: <strong>{totals.occupied}</strong>
            {' · '}{t('staffing.vacant')}: <strong>{totals.vacant}</strong>
            {totals.established > 0 && ` · ${percent}%`}
          </div>
        </div>
        {isAdmin && !adding && (
          <button className="btn btn-sm" onClick={() => { setAdding(true); setEditingId(null) }}>
            + {t('staffing.addLine')}
          </button>
        )}
      </div>

      {error && (
        <div style={{ padding: '10px 14px' }}>
          <div className="alert alert-bad" style={{ margin: 0 }}>{error}</div>
        </div>
      )}

      {totals.established > 0 && (
        <div style={{ padding: '0 14px', marginTop: 10 }}>
          <div style={{ height: 6, borderRadius: 3, overflow: 'hidden',
                        background: 'var(--slate-200)' }}>
            <div style={{ height: '100%', width: `${percent}%`,
                          background: percent === 100
                            ? 'var(--ok)' : 'var(--accent)' }} />
          </div>
        </div>
      )}

      {adding && isAdmin && (
        <LineForm unitId={unitId} positions={used} grades={grades}
                  onCancel={() => setAdding(false)} onSaved={applied}
                  onError={setError} />
      )}

      {data.lines.length === 0 && !adding ? (
        <div className="empty">
          {t('staffing.noLines')}
          {isAdmin && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              {t('staffing.noLinesHint')}
            </div>
          )}
        </div>
      ) : (
        <table>
          <thead><tr>
            <th className="col-shrink">{t('staffing.position')}</th>
            <th className="col-shrink">{t('staffing.grade')}</th>
            <th className="col-shrink num">{t('staffing.headcount')}</th>
            <th className="col-shrink num">{t('staffing.occupied')}</th>
            <th className="col-shrink num">{t('staffing.vacant')}</th>
            <th className="col-grow">{t('staffing.holders')}</th>
            {isAdmin && <th className="col-actions" />}
          </tr></thead>
          <tbody>
            {data.lines.map((line) => (
              <React.Fragment key={line.id}>
                <tr className={!line.is_active ? 'status-row status-closed' : line.over_established > 0 ? 'status-row status-warning' : ''}>
                  <td>
                    <strong>{label(line)}</strong>
                    <div className="muted mono" style={{ fontSize: 11 }}>
                      {line.position_code}
                      {!line.is_active && (
                        <span className="badge badge-closed" style={{ marginLeft: 6 }}>
                          {t('staffing.inactive')}
                        </span>
                      )}
                    </div>
                    {line.notes && (
                      <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                        {line.notes}
                      </div>
                    )}
                  </td>
                  <td className="muted">{line.grade || '—'}</td>
                  <td className="num">
                    {isAdmin ? (
                      <div style={{ display: 'flex', gap: 3,
                                    justifyContent: 'flex-end',
                                    alignItems: 'center' }}>
                        <button className="btn btn-ghost btn-sm" disabled={busy}
                                style={{ padding: '1px 7px' }}
                                onClick={() => changeHeadcount(line, -1)}>−</button>
                        <strong style={{ minWidth: 22, textAlign: 'center' }}>
                          {line.headcount}
                        </strong>
                        <button className="btn btn-ghost btn-sm" disabled={busy}
                                style={{ padding: '1px 7px' }}
                                onClick={() => changeHeadcount(line, +1)}>+</button>
                      </div>
                    ) : <strong>{line.headcount}</strong>}
                  </td>
                  <td className="num">{line.occupied}</td>
                  <td className="num">
                    {line.vacant > 0
                      ? <span className="badge badge-ok">{line.vacant}</span>
                      : <span className="muted">0</span>}
                    {line.over_established > 0 && (
                      <span className="badge badge-warn" style={{ marginLeft: 4 }}>
                        +{line.over_established}
                      </span>
                    )}
                  </td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {line.holders.length === 0 ? '—'
                      : line.holders.map((h) => h.full_name).join(', ')}
                  </td>
                  {isAdmin && (
                    <td>
                      <div className="btn-row">
                        <button className="btn btn-ghost btn-sm"
                                onClick={() => {
                                  setEditingId(editingId === line.id ? null : line.id)
                                  setAdding(false)
                                }}>
                          {t('common.edit')}
                        </button>
                        <button className="btn btn-danger btn-sm"
                                disabled={line.occupied > 0}
                                title={line.occupied > 0 ? t('staffing.deleteWarn') : ''}
                                onClick={() => remove(line)}>×</button>
                      </div>
                    </td>
                  )}
                </tr>
                {editingId === line.id && isAdmin && (
                  <tr><td colSpan={7} style={{ padding: 0 }}>
                    <LineForm line={line} grades={grades}
                              onCancel={() => setEditingId(null)}
                              onSaved={applied} onError={setError} />
                  </td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}

      {data.off_establishment.length > 0 && (
        <div style={{ borderTop: '1px solid var(--slate-200)',
                      padding: '11px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="badge badge-warn">{t('staffing.offEstablishment')}</span>
            <span className="muted" style={{ fontSize: 11.5 }}>
              {t('staffing.offEstablishmentHint')}
            </span>
          </div>
          <table style={{ marginTop: 8 }}>
            <tbody>
              {data.off_establishment.map((row) => (
                <tr key={row.position_id}>
                  <td>{row[`position_${lang}`] || row.position_ru}</td>
                  <td className="num">{row.occupied}</td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {row.holders.map((h) => h.full_name).join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------- line form */

function LineForm({ unitId, line, positions, grades, onSaved, onCancel,
                    onError }) {
  const { t, pick } = useI18n()
  const editing = Boolean(line)
  const [form, setForm] = useState({
    position_id: '',
    headcount: editing ? String(line.headcount) : '1',
    grade_id: editing && line.grade_id ? String(line.grade_id) : '',
    notes: editing ? (line.notes || '') : '',
    is_active: editing ? line.is_active : true,
  })
  const [busy, setBusy] = useState(false)

  const submit = async (ev) => {
    ev.preventDefault()
    onError(null)
    setBusy(true)
    try {
      const body = {
        headcount: Number(form.headcount),
        grade_id: form.grade_id ? Number(form.grade_id) : null,
        notes: form.notes.trim() || null,
        is_active: form.is_active,
      }
      const r = editing
        ? await api.staffingUpdate(line.id, body)
        : await api.staffingAdd(unitId,
            { ...body, position_id: Number(form.position_id) })
      onSaved(r.data)
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}
          style={{ padding: '12px 14px', background: 'var(--surface-2)',
                   borderBottom: '1px solid var(--slate-200)' }}>
      <div className="form-row-3">
        {!editing && (
          <div className="field">
            <label>{t('staffing.position')}</label>
            <select value={form.position_id} required
                    onChange={(e) => setForm({ ...form, position_id: e.target.value })}>
              <option value="">—</option>
              {(positions || []).map((p) => (
                <option key={p.id} value={p.id}>{pick(p)}</option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label>{t('staffing.headcount')}</label>
          <input type="number" min="0" max="10000" required value={form.headcount}
                 onChange={(e) => setForm({ ...form, headcount: e.target.value })} />
        </div>
        <div className="field">
          <label>{t('staffing.grade')}</label>
          <select value={form.grade_id}
                  onChange={(e) => setForm({ ...form, grade_id: e.target.value })}>
            <option value="">—</option>
            {(grades || []).map((g) => (
              <option key={g.id} value={g.id}>{pick(g)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="field">
        <label>{t('staffing.notes')}</label>
        <input value={form.notes}
               onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14,
                    flexWrap: 'wrap' }}>
        <div className="btn-row">
          <button className="btn btn-sm" type="submit" disabled={busy}>
            {t('common.save')}
          </button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={onCancel}>
            {t('common.cancel')}
          </button>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 12.5 }}>
          <input type="checkbox" checked={form.is_active}
                 style={{ width: 'auto' }}
                 onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          {t('staffing.active')}
        </label>
      </div>
    </form>
  )
}
