import React from 'react'
import { useI18n } from '../i18n'
import { candidateText } from '../i18n/candidateMethodology'
import { newSource, optionValue, sourceDefinition, sourceKey, sourceLabel, sourceOptions, defaultRuleValue, ruleOperators } from '../candidateSources'

function RuleValue({ source, definition, rule, options, copy, lang, onChange }) {
  if (rule.operator === 'present') return null
  if (options.length) return <label>{copy.value}<select required value={String(rule.value)} onChange={e => {
    const selected = options.find(option => String(optionValue(option)) === e.target.value)
    onChange(optionValue(selected))
  }}><option value="" disabled>{copy.choose}</option>{options.map(option => <option key={String(optionValue(option))}
    value={String(optionValue(option))}>{sourceLabel(option, lang)}</option>)}</select></label>
  if (source.kind === 'tab_field' && definition?.field_type === 'date') return <>
    <label>{copy.dateReference}<select value={rule.value === 'today' ? 'today' : 'fixed'}
      onChange={e => onChange(e.target.value === 'today' ? 'today' : '')}>
      <option value="today">{copy.today}</option><option value="fixed">{copy.fixedDate}</option>
    </select></label>
    {rule.value !== 'today' && <label>{copy.value}<input type="date" required value={rule.value} onChange={e => onChange(e.target.value)} /></label>}
  </>
  if (definition?.field_type === 'text') return <label>{copy.value}<input type="text" required maxLength={4000}
    value={rule.value} onChange={e => onChange(e.target.value)} /></label>
  return <label>{copy.value}<input type="number" required step="any" value={rule.value ?? ''}
    onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))} /></label>
}

export default function CandidateSourceEditor({ criterion, catalog, disabled, onChange }) {
  const { lang } = useI18n()
  const copy = candidateText(lang)
  const source = criterion.source
  const definition = sourceDefinition(source, catalog)
  const options = sourceOptions(source, definition)
  const operators = ruleOperators(source, definition)
  const tabs = new Map()
  for (const field of catalog?.tab_fields || []) {
    if (!tabs.has(field.section_id)) tabs.set(field.section_id, [])
    tabs.get(field.section_id).push(field)
  }
  function setOperator(index, operator) {
    const rules = source.rules.map((rule, i) => i !== index ? rule : { ...rule, operator,
      value: operator === 'present' || rule.operator === 'present' ? defaultRuleValue(source, definition || {}, operator) : rule.value })
    onChange({ ...source, rules })
  }
  const setRule = (index, key, value) => onChange({ ...source, rules: source.rules.map((rule, at) => at === index ? { ...rule, [key]: value } : rule) })
  return <fieldset className="candidate-source-editor" disabled={disabled}>
    <legend>{copy.sourceSetup}</legend>
    <div className="candidate-source-selects">
      <label>{copy.source}<select value={sourceKey(source)} onChange={e => onChange(newSource(e.target.value, catalog, criterion.max_points))}>
        <option value="manual">{copy.manual}</option>
        <optgroup label={copy.standardFacts}>{(catalog?.facts || []).map(fact => <option key={fact.code} value={`fact:${fact.code}`}>{sourceLabel(fact, lang)}</option>)}</optgroup>
        <optgroup label={copy.dossierFields}>{(catalog?.fields || []).map(field => <option key={field.id} value={`field:${field.id}`}>{sourceLabel(field, lang)}{field.visibility === 'admin' ? ` · ${copy.privateField}` : ''}</option>)}</optgroup>
        {[...tabs].map(([id, fields]) => <optgroup key={id} label={`${copy.dossierTab} · ${fields[0][`section_${lang}`] || fields[0].section_ru}`}>
          {fields.map(field => <option key={field.id} value={`tab:${field.id}`}>{sourceLabel(field, lang)}{field.visibility === 'admin' ? ` · ${copy.privateField}` : ''}</option>)}
        </optgroup>)}
      </select></label>
      {!!definition?.arguments?.length && <label>{copy.language}<select value={source.argument ?? ''} onChange={e => onChange({ ...source, argument: Number(e.target.value) })}>
        {definition.arguments.map(option => <option key={optionValue(option)} value={optionValue(option)}>{sourceLabel(option, lang)}</option>)}
      </select></label>}
      {!!definition?.scales?.length && <label>{copy.scale}<select value={source.scale_id ?? ''} onChange={e => {
        const next = { ...source, scale_id: Number(e.target.value) }
        const first = sourceOptions(next, definition)[0]
        onChange({ ...next, rules: source.rules.map(rule => ({ ...rule, value: optionValue(first) ?? '' })) })
      }}>
        {definition.scales.map(option => <option key={optionValue(option)} value={optionValue(option)}>{sourceLabel(option, lang)}</option>)}
      </select></label>}
    </div>
    {source && source.kind !== 'manual' && <>
      {!definition && <p className="alert alert-bad">{copy.sourceUnavailable}</p>}
      {definition?.visibility === 'admin' && <p className="candidate-info">{copy.privateSourceHint}</p>}
      {source.kind === 'tab_field' && <p className="candidate-info">{copy.repeatableFieldHint}</p>}
      <div className="candidate-rule-list">
        {(source.rules || []).map((rule, index) => <div className="candidate-rule" key={index}>
          <label>{copy.condition}<select value={rule.operator} onChange={e => setOperator(index, e.target.value)}>{operators.map(operator => <option key={operator} value={operator}>{copy[`operator_${operator}`]}</option>)}</select></label>
          <RuleValue source={source} definition={definition} rule={rule} options={options} copy={copy} lang={lang}
            onChange={value => setRule(index, 'value', value)} />
          <label>{copy.points}<input type="number" required min="0" max={criterion.max_points} step="0.01" value={rule.points} onChange={e => setRule(index, 'points', e.target.value)} /></label>
          <button type="button" className="btn btn-ghost btn-sm" disabled={disabled || source.rules.length <= 1} aria-label={`${copy.removeRule} ${index + 1}`} onClick={() => onChange({ ...source, rules: source.rules.filter((_, at) => at !== index) })}>{copy.remove}</button>
        </div>)}
      </div>
      <div className="candidate-toolbar"><button type="button" className="btn btn-ghost btn-sm" disabled={disabled || !definition || (source.rules?.length || 0) >= 20} onClick={() => onChange({ ...source, rules: [...(source.rules || []), { operator: operators[0], value: defaultRuleValue(source, definition, operators[0]), points: criterion.max_points }] })}>{copy.addRule}</button>
        <small className="muted">{copy.ruleHint}</small></div>
    </>}
  </fieldset>
}
