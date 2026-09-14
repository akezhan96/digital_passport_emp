import React, { useEffect, useState, useMemo } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'

/**
 * Turns a requirement type's form specification into real inputs, so an HR
 * user never types JSON. The spec lives in the database
 * (ref_requirement_types.condition_schema), which means a new requirement
 * type gets a usable form without touching this component.
 *
 * Supported field kinds: number | ref | boolean | list
 */
export default function ConditionBuilder({ schema, value, onChange }) {
  const { t, lang, pick } = useI18n()
  const [catalogs, setCatalogs] = useState({})

  const fields = useMemo(() => schema?.fields || [], [schema])

  // Load every catalogue the spec refers to, once per schema.
  useEffect(() => {
    const needed = new Set()
    const walk = (list) => (list || []).forEach((f) => {
      if (f.kind === 'ref' && f.catalog) needed.add(f.catalog)
      if (f.kind === 'list') walk(f.item_fields)
    })
    walk(fields)

    const missing = [...needed].filter((c) => !catalogs[c])
    if (missing.length === 0) return

    Promise.all(missing.map((c) =>
      api.refList(c).then((r) => [c, r.data.data]).catch(() => [c, []])))
      .then((pairs) => setCatalogs((prev) => ({ ...prev, ...Object.fromEntries(pairs) })))
  }, [fields, catalogs])

  const label = (f) => f[`label_${lang}`] || f.label_ru || f.label_en || f.key
  const suffix = (f) => f[`suffix_${lang}`] || f.suffix_ru || f.suffix_en || ''

  const setKey = (key, next) => onChange({ ...(value || {}), [key]: next })

  if (!schema) {
    return <div className="alert alert-info">{t('condition.selectTypeFirst')}</div>
  }

  const hint = schema[`hint_${lang}`] || schema.hint_ru || schema.hint_en

  return (
    <div>
      {hint && (
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
          {hint}
        </div>
      )}

      {fields.map((f) => (
        <FieldRow key={f.key} field={f} label={label(f)} suffix={suffix(f)}
                  catalogs={catalogs} lang={lang} pick={pick} t={t}
                  value={(value || {})[f.key]}
                  onChange={(next) => setKey(f.key, next)} />
      ))}
    </div>
  )
}

function FieldRow({ field, label, suffix, catalogs, lang, pick, t,
                    value, onChange }) {
  if (field.kind === 'list') {
    return <ListField field={field} label={label} catalogs={catalogs}
                      lang={lang} pick={pick} t={t}
                      value={value} onChange={onChange} />
  }
  return (
    <div className="field">
      <label>
        {label}
        {field.required && <span style={{ color: 'var(--bad)' }}> *</span>}
      </label>
      <ScalarInput field={field} suffix={suffix} catalogs={catalogs}
                   pick={pick} t={t} value={value} onChange={onChange} />
    </div>
  )
}

function ScalarInput({ field, suffix, catalogs, pick, t, value, onChange }) {
  if (field.kind === 'ref') {
    const options = catalogs[field.catalog] || []
    const valueField = field.value_field || 'code'
    return (
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">—</option>
        {options.map((o) => (
          <option key={o.id} value={o[valueField]}>
            {pick(o)}{o.code && pick(o) !== o.code ? ` (${o.code})` : ''}
          </option>
        ))}
      </select>
    )
  }

  if (field.kind === 'boolean') {
    return (
      <label style={{ display: 'flex', alignItems: 'center', gap: 8,
                      fontWeight: 400, marginTop: 4 }}>
        <input type="checkbox" style={{ width: 'auto' }}
               checked={value === undefined ? Boolean(field.default) : Boolean(value)}
               onChange={(e) => onChange(e.target.checked)} />
        <span className="muted" style={{ fontSize: 12.5 }}>
          {(value === undefined ? field.default : value) ? t('common.yes') : t('common.no')}
        </span>
      </label>
    )
  }

  // number
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <input type="number" min={field.min ?? 0} step={field.step ?? 1}
             style={{ maxWidth: 180 }}
             value={value ?? (field.default ?? '')}
             onChange={(e) => onChange(e.target.value === ''
               ? undefined : Number(e.target.value))} />
      {suffix && <span className="muted" style={{ fontSize: 12.5 }}>{suffix}</span>}
    </div>
  )
}

/** A repeatable group, e.g. "English B2 OR German B2". */
function ListField({ field, label, catalogs, lang, pick, t, value, onChange }) {
  const items = Array.isArray(value) ? value : []
  const itemFields = field.item_fields || []

  const blank = () => Object.fromEntries(
    itemFields.filter((f) => f.default !== undefined).map((f) => [f.key, f.default]))

  const addLabel = field[`add_${lang}`] || field.add_ru || t('condition.addItem')

  const setItem = (index, key, next) => {
    const copy = items.map((row, i) =>
      i === index ? { ...row, [key]: next } : row)
    onChange(copy)
  }

  return (
    <div className="field">
      <label>
        {label}
        {field.required && <span style={{ color: 'var(--bad)' }}> *</span>}
      </label>

      {items.length === 0 && (
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>
          {t('condition.anyOf')}
        </div>
      )}

      {items.map((row, index) => (
        <div key={index}
             style={{ border: '1px solid var(--slate-200)', borderRadius: 6,
                      padding: '10px 12px', marginBottom: 8,
                      background: 'var(--slate-50)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', marginBottom: 6 }}>
            <span className="muted" style={{ fontSize: 11.5, fontWeight: 600 }}>
              {index + 1}
            </span>
            <button type="button" className="btn btn-danger btn-sm"
                    onClick={() => onChange(items.filter((_, i) => i !== index))}>
              {t('condition.removeItem')}
            </button>
          </div>
          <div className="form-row-3">
            {itemFields.map((f) => (
              <div className="field" key={f.key} style={{ marginBottom: 0 }}>
                <label>{f[`label_${lang}`] || f.label_ru || f.key}</label>
                <ScalarInput field={f} suffix="" catalogs={catalogs}
                             pick={pick} t={t} value={row[f.key]}
                             onChange={(next) => setItem(index, f.key, next)} />
              </div>
            ))}
          </div>
        </div>
      ))}

      <button type="button" className="btn btn-ghost btn-sm"
              onClick={() => onChange([...items, blank()])}>
        + {addLabel}
      </button>
    </div>
  )
}

/**
 * Read-only, human-readable rendering of a stored condition, for tables.
 * Falls back to showing the raw code when a catalogue row is not loaded.
 */
export function ConditionSummary({ schema, condition, catalogs = {} }) {
  const { lang, pick } = useI18n()
  if (!condition || Object.keys(condition).length === 0) return <span>—</span>

  const fields = schema?.fields || []
  const specFor = (key) => fields.find((f) => f.key === key)
  const labelOf = (f, key) =>
    (f && (f[`label_${lang}`] || f.label_ru)) || key

  const resolve = (f, raw) => {
    if (!f || f.kind !== 'ref') return String(raw)
    const row = (catalogs[f.catalog] || [])
      .find((o) => String(o[f.value_field || 'code']) === String(raw))
    return row ? pick(row) : String(raw)
  }

  const parts = []
  Object.entries(condition).forEach(([key, raw]) => {
    const f = specFor(key)

    if (Array.isArray(raw)) {
      const rows = raw.map((item) => {
        const inner = (f?.item_fields || [])
          .filter((sub) => sub.kind !== 'boolean')
          .map((sub) => resolve(sub, item[sub.key]))
          .filter(Boolean)
        return inner.join(' ')
      }).filter(Boolean)
      if (rows.length) parts.push(`${labelOf(f, key)}: ${rows.join(' / ')}`)
      return
    }

    if (typeof raw === 'boolean') {
      if (raw) parts.push(labelOf(f, key))
      return
    }

    if (raw === '' || raw === undefined || raw === null) return

    const suffix = f?.[`suffix_${lang}`] || f?.suffix_ru || ''
    parts.push(`${labelOf(f, key)}: ${resolve(f, raw)}${suffix ? ' ' + suffix : ''}`)
  })

  return (
    <span style={{ fontSize: 12.5 }}>
      {parts.length ? parts.join(' · ') : '—'}
    </span>
  )
}
