export const hasDossierSource = criterion => ['dossier_field', 'dossier_fact', 'tab_field'].includes(criterion.source?.kind)
export const optionValue = option => option && typeof option === 'object' ? option.value : option
export function sourceLabel(item, lang) {
  if (!item || typeof item !== 'object') return String(item ?? '')
  const label = item[`name_${lang}`] || item[`label_${lang}`] || item.name_ru || item.label_ru || item.label || String(item.value ?? '')
  const tab = item[`section_${lang}`] || item.section_ru
  return tab ? `${tab} · ${label}` : label
}
export const sourceKey = source => source?.kind === 'tab_field' ? `tab:${source.field_id}` : source?.kind === 'dossier_field' ? `field:${source.field_id}` : source?.kind === 'dossier_fact' ? `fact:${source.fact}` : 'manual'
export const sourceDefinition = (source, catalog) => source?.kind === 'tab_field' ? catalog?.tab_fields?.find(field => field.id === source.field_id) : source?.kind === 'dossier_field'
  ? catalog?.fields?.find(field => field.id === source.field_id)
  : source?.kind === 'dossier_fact' ? catalog?.facts?.find(fact => fact.code === source.fact) : null

export function sourceOptions(source, definition) {
  if (!definition) return []
  const options = definition.field_type === 'boolean' && !definition.options?.length
    ? [{ value: true, name_ru: 'Да', name_kk: 'Иә' }, { value: false, name_ru: 'Нет', name_kk: 'Жоқ' }] : definition.options || []
  return source?.fact === 'language_level' ? options.filter(option => option.scale_id === source.scale_id) : options
}

export function ruleOperators(source, definition) {
  const ordered = ['number', 'date'].includes(definition?.field_type)
  const operators = ordered ? ['gte', 'lte', 'eq'] : ['eq']
  return source?.kind === 'tab_field' ? [...operators, 'present'] : operators
}

export function defaultRuleValue(source, definition, operator) {
  if (operator === 'present') return ''
  const options = sourceOptions(source, definition)
  if (options.length) return optionValue(options[0])
  if (definition.field_type === 'date') return 'today'
  return definition.field_type === 'text' ? '' : 0
}

export function newSource(key, catalog, maximum) {
  if (key === 'manual') return null
  const [kind, id] = key.split(':')
  const source = kind === 'fact' ? { kind: 'dossier_fact', fact: id }
    : { kind: kind === 'tab' ? 'tab_field' : 'dossier_field', field_id: Number(id) }
  const definition = sourceDefinition(source, catalog)
  if (!definition) return null
  if (definition.arguments?.length) source.argument = optionValue(definition.arguments[0])
  if (definition.scales?.length) source.scale_id = optionValue(definition.scales[0])
  const operator = source.kind === 'tab_field' && definition.field_type === 'text' ? 'present' : ruleOperators(source, definition)[0]
  source.rules = [{ operator, value: defaultRuleValue(source, definition, operator), points: maximum }]
  return source
}

export function evaluationPayload(data, values, technical, note) {
  return {
    methodology_id: data.methodology.id, expected_revision: data.revision,
    technical_profile: technical, note,
    scores: data.methodology.criteria.filter(c => c.enabled && (technical || c.block !== 'technical')
      && !hasDossierSource(c) && values[c.position] !== undefined && values[c.position] !== '')
      .map(c => ({ position: c.position, points: values[c.position] })),
  }
}

export const hasApplicableSources = (criteria, technical) => criteria.some(c => c.enabled && hasDossierSource(c) && (technical || c.block !== 'technical'))

export function methodologySections(method) {
  return [...(method?.sections || [
    { key: 'general', name_ru: 'Общие', name_kk: 'Жалпы', kind: 'general', position: 0 },
    { key: 'technical', name_ru: 'Технические', name_kk: 'Техникалық', kind: 'technical', position: 1 },
    { key: 'psychological', name_ru: 'Психологические', name_kk: 'Психологиялық', kind: 'psychological', position: 2 },
  ])].sort((a, b) => a.position - b.position)
}

export const criterionSection = criterion => criterion.section_key || criterion.block
export function orderedCriteria(method, sectionKey) {
  const sections = methodologySections(method)
  const sectionRanks = Object.fromEntries(sections.map((section, index) => [section.key, index]))
  return [...(method?.criteria || [])].filter(c => !sectionKey || criterionSection(c) === sectionKey)
    .sort((a, b) => (sectionRanks[criterionSection(a)] ?? 999) - (sectionRanks[criterionSection(b)] ?? 999)
      || (a.display_order ?? a.position) - (b.display_order ?? b.position) || a.position - b.position)
}

export function moveItem(items, from, direction) {
  const next = [...items], to = from + direction
  if (from < 0 || to < 0 || to >= next.length) return next
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}
