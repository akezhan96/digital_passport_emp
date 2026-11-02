import React, { useEffect, useState, useMemo } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'

/**
 * Lets the user assemble their own analytics query from fields, operators and
 * values. The field catalogue comes from the server and is built from live
 * data, so a new competency or an administrator-defined custom field turns up
 * here without any change to this component.
 */
export default function QueryBuilder({ value, onChange, onError }) {
  const { t, lang } = useI18n()
  const [catalogue, setCatalogue] = useState(null)

  useEffect(() => {
    api.analyticsFields()
      .then((r) => setCatalogue(r.data))
      .catch((e) => onError?.(errorMessage(e)))
  }, [onError])

  const byCode = useMemo(() => {
    const map = {}
    ;(catalogue?.groups || []).forEach((g) =>
      g.fields.forEach((f) => { map[f.code] = f }))
    return map
  }, [catalogue])

  if (!catalogue) return <div className="spinner" />

  const label = (o) => (o?.[`name_${lang}`] || o?.name_ru || '')
  const definition = value.definition || { match: 'all', conditions: [] }
  const conditions = definition.conditions || []

  const setDefinition = (next) => onChange({ ...value, definition: next })
  const setCondition = (index, patch) => setDefinition({
    ...definition,
    conditions: conditions.map((c, i) => (i === index ? { ...c, ...patch } : c)),
  })

  const addCondition = () => setDefinition({
    ...definition,
    conditions: [...conditions, { field: '', operator: '', value: '' }],
  })

  const removeCondition = (index) => setDefinition({
    ...definition,
    conditions: conditions.filter((_, i) => i !== index),
  })

  // Changing the field invalidates the operator and value chosen for the old one.
  const pickField = (index, code) => {
    const field = byCode[code]
    setCondition(index, {
      field: code,
      argument: field?.argument ? '' : undefined,
      operator: field?.operators?.[0]?.code || 'eq',
      value: field?.kind === 'boolean' ? true : '',
    })
  }

  return (
    <div>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        {t('builder.hint')}
      </div>

      <div className="field" style={{ maxWidth: 320 }}>
        <label>{t('builder.match')}</label>
        <select value={definition.match || 'all'}
                onChange={(e) => setDefinition({ ...definition,
                  match: e.target.value })}>
          {catalogue.match_modes.map((m) => (
            <option key={m.code} value={m.code}>{label(m)}</option>
          ))}
        </select>
      </div>

      {conditions.length === 0 && (
        <div className="muted" style={{ fontSize: 12.5, margin: '10px 0' }}>
          {t('builder.noConditions')}
        </div>
      )}

      {conditions.map((condition, index) => {
        const field = byCode[condition.field]
        const operator = (field?.operators || [])
          .find((o) => o.code === condition.operator)
        return (
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
                      onClick={() => removeCondition(index)}>
                {t('builder.removeCondition')}
              </button>
            </div>

            <div className="form-row-3">
              <div className="field" style={{ marginBottom: 0 }}>
                <label>{t('builder.field')}</label>
                <select value={condition.field || ''}
                        onChange={(e) => pickField(index, e.target.value)}>
                  <option value="">—</option>
                  {catalogue.groups.map((group) => (
                    <optgroup key={group.name_ru} label={label(group)}>
                      {group.fields.map((f) => (
                        <option key={f.code} value={f.code}>{label(f)}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              {field?.argument && (
                <div className="field" style={{ marginBottom: 0 }}>
                  <label>{label(field.argument) || t('builder.argument')}</label>
                  <select value={condition.argument || ''}
                          onChange={(e) => setCondition(index,
                            { argument: e.target.value })}>
                    <option value="">—</option>
                    {field.argument.options.map((o) => (
                      <option key={o.value} value={o.value}>{label(o)}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="field" style={{ marginBottom: 0 }}>
                <label>{t('builder.operator')}</label>
                <select value={condition.operator || ''} disabled={!field}
                        onChange={(e) => setCondition(index,
                          { operator: e.target.value })}>
                  {(field?.operators || []).map((o) => (
                    <option key={o.code} value={o.code}>{label(o)}</option>
                  ))}
                </select>
              </div>
            </div>

            {field && operator
              && !['is_true', 'is_false', 'not_empty'].includes(operator.code) && (
              <div className="field" style={{ marginTop: 8, marginBottom: 0 }}>
                <label>
                  {t('builder.value')}
                  {field.suffix_ru && (
                    <span className="muted">
                      {' '}({field[`suffix_${lang}`] || field.suffix_ru})
                    </span>
                  )}
                </label>
                <ValueInput field={field} operator={operator.code} t={t}
                            label={label} value={condition.value}
                            onChange={(v) => setCondition(index, { value: v })} />
              </div>
            )}
          </div>
        )
      })}

      <div className="btn-row" style={{ marginTop: 4 }}>
        <button type="button" className="btn btn-ghost btn-sm"
                onClick={addCondition}>
          + {t('builder.addCondition')}
        </button>
      </div>

      <div className="field" style={{ marginTop: 14, maxWidth: 360 }}>
        <label>{t('builder.groupBy')}</label>
        <select value={value.group_by || ''}
                onChange={(e) => onChange({ ...value,
                  group_by: e.target.value || null })}>
          <option value="">{t('builder.noGrouping')}</option>
          {catalogue.group_by.map((f) => (
            <option key={f.code} value={f.code}>{label(f)}</option>
          ))}
        </select>
      </div>
    </div>
  )
}

function ValueInput({ field, operator, value, onChange, t, label }) {
  if (operator === 'between') {
    const pair = Array.isArray(value) ? value : ['', '']
    return (
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input type="number" style={{ maxWidth: 140 }} placeholder={t('builder.valueFrom')}
               value={pair[0] ?? ''}
               onChange={(e) => onChange([e.target.value, pair[1]])} />
        <span className="muted">—</span>
        <input type="number" style={{ maxWidth: 140 }} placeholder={t('builder.valueTo')}
               value={pair[1] ?? ''}
               onChange={(e) => onChange([pair[0], e.target.value])} />
      </div>
    )
  }

  if (field.options) {
    if (operator === 'in') {
      const chosen = Array.isArray(value) ? value : []
      const toggle = (v) => onChange(chosen.includes(v)
        ? chosen.filter((x) => x !== v) : [...chosen, v])
      return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10,
                      padding: '6px 0' }}>
          {field.options.map((o) => (
            <label key={o.value} style={{ display: 'flex', alignItems: 'center',
                                          gap: 6, fontWeight: 400, margin: 0 }}>
              <input type="checkbox" style={{ width: 'auto' }}
                     checked={chosen.includes(o.value)}
                     onChange={() => toggle(o.value)} />
              <span style={{ fontSize: 13 }}>{label(o)}</span>
            </label>
          ))}
        </div>
      )
    }
    return (
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {field.options.map((o) => (
          <option key={o.value} value={o.value}>{label(o)}</option>
        ))}
      </select>
    )
  }

  if (field.kind === 'number') {
    return (
      <input type="number" step="any" style={{ maxWidth: 200 }}
             value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    )
  }

  return <input value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
}
