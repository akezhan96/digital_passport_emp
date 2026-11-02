import { useRef } from 'react'
import { useI18n } from './i18n'
import { employeeDirectoryText } from './i18n/employeeDirectory'
import { formFingerprint } from './formChanges'
import { useUnsavedChanges } from './useUnsavedChanges'
import { CANDIDATE_SCOPE } from './unsavedChanges'

// All editable sections of one dossier share its existing navigation guard.
// Call accept only after a confirmed save (or an explicitly accepted discard).
export function useFormChanges(value, { enabled = true, scope = CANDIDATE_SCOPE } = {}) {
  const { lang } = useI18n()
  const baseline = useRef(formFingerprint(value))
  const markSaved = useUnsavedChanges(enabled && formFingerprint(value) !== baseline.current,
    employeeDirectoryText(lang).discard, scope)
  return (nextValue = value) => {
    baseline.current = formFingerprint(nextValue)
    markSaved()
  }
}
