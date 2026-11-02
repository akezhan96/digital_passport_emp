import { useLayoutEffect, useRef } from 'react'
import { registerUnsavedChanges } from './unsavedChanges'

export function useUnsavedChanges(dirty, message, scope) {
  const current = useRef({ dirty, message })
  useLayoutEffect(() => { current.current = { dirty, message } }, [dirty, message])
  useLayoutEffect(() => registerUnsavedChanges(() => current.current, scope), [scope])
  // Saving can notify a parent before React commits the new state. Clear the
  // guard synchronously only after the server has confirmed that save.
  return () => { current.current = { ...current.current, dirty: false } }
}
