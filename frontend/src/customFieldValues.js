export const customOptionValue = option => option && typeof option === 'object' ? option.value : option

export function customOptionLabel(option, lang) {
  if (option && typeof option === 'object') {
    return String(option[`name_${lang}`] || option.name_ru || option.label || (option.value ?? ''))
  }
  return String(option ?? '')
}

export function displayCustomFieldValue(field, value, lang, yes, no) {
  if (value == null || value === '') return '—'
  if (field.field_type === 'boolean') {
    if (value === true || value === 'true') return yes
    if (value === false || value === 'false') return no
  }
  if (field.field_type === 'select') {
    const option = (field.options || []).find(item => String(customOptionValue(item)) === String(value))
    if (option !== undefined) return customOptionLabel(option, lang)
  }
  return String(value)
}
