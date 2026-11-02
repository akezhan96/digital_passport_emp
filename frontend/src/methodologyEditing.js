import { methodologySections, orderedCriteria } from './candidateSources.js'

// A section key and a criterion position survive cloning; database row IDs do not.
export function renameMethodologyItem(method, target, names) {
  const translated = { name_ru: names.name_ru.trim(), name_kk: names.name_kk.trim() }
  if (!translated.name_ru || !translated.name_kk) return null
  if (target.kind === 'section') {
    const sections = methodologySections(method)
    if (!sections.some(section => section.key === target.sectionKey)) return null
    return { ...method, sections: sections.map(section => section.key === target.sectionKey ? { ...section, ...translated } : section) }
  }
  if (target.kind !== 'criterion' || !method.criteria.some(criterion => criterion.position === target.position)) return null
  return { ...method, criteria: method.criteria.map(criterion => criterion.position === target.position ? { ...criterion, ...translated } : criterion) }
}

export function methodologyUpdatePayload(method) {
  return {
    name_ru: method.name_ru, name_kk: method.name_kk, expected_revision: method.revision,
    sections: methodologySections(method).map((section, index) => ({ ...section, position: index })),
    criteria: orderedCriteria(method).map(({ id, position, section_key, block, name_ru, name_kk, max_points, enabled, source }, index) =>
      ({ id, position, section_key: section_key || block, display_order: index, name_ru, name_kk, max_points, enabled, source: source || null })),
  }
}

export async function saveRenamedVersion(api, method, target, names, existingDraft, onDraft) {
  const { data: draft } = existingDraft ? await api.model(existingDraft.id) : await api.clone(method.id)
  onDraft(draft)
  const renamed = renameMethodologyItem(draft, target, names)
  if (!renamed) {
    const error = new Error('The renamed item is no longer present')
    error.code = 'RENAME_TARGET_MISSING'
    throw error
  }
  return (await api.update(draft.id, methodologyUpdatePayload(renamed))).data
}
