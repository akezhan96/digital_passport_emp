// Compare form values as they appear in inputs: selecting the original numeric
// option again must not turn an unchanged form into a dirty one.
export function formFingerprint(value) {
  const normalize = item => {
    if (item == null) return ''
    if (Array.isArray(item)) return item.map(normalize)
    if (typeof item === 'object') return Object.fromEntries(Object.keys(item).sort()
      .map(key => [key, normalize(item[key])]).filter(([, entry]) => entry !== ''))
    return String(item)
  }
  return JSON.stringify(normalize(value))
}
