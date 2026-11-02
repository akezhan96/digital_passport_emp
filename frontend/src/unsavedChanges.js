// This registry stores only dirty flags and translated prompts, never form data.
// It is shared by SPA navigation, local tabs/dialogs and beforeunload.
export const CANDIDATE_SCOPE = 'candidate-evaluation'
export const METHODOLOGY_SCOPE = 'candidate-methodology'

export function createUnsavedChangesGuard({ target, confirm } = {}) {
  const entries = new Map()
  const dirtyEntries = scope => [...entries.values()].filter(entry =>
    (!scope || entry.scope === scope || entry.scope?.startsWith(`${scope}:`)) && entry.read().dirty)
  const beforeUnload = event => {
    const entry = dirtyEntries()[0]
    if (!entry) return
    event.preventDefault()
    // Modern browsers show their own translated system prompt. The return
    // value also supports engines that still display the provided message.
    event.returnValue = entry.read().message
    return event.returnValue
  }
  const guard = {
    register(read, scope) {
      const key = Symbol('unsaved form')
      if (!entries.size) target?.addEventListener('beforeunload', beforeUnload)
      entries.set(key, { read, scope })
      return () => {
        entries.delete(key)
        if (!entries.size) target?.removeEventListener('beforeunload', beforeUnload)
      }
    },
    confirmLeave(scope) {
      const entry = dirtyEntries(scope)[0]
      return !entry || Boolean(confirm?.(entry.read().message))
    },
    run(action, { event, scope } = {}) {
      if (!guard.confirmLeave(scope)) {
        event?.preventDefault()
        return false
      }
      action()
      return true
    },
  }
  return guard
}

const shared = createUnsavedChangesGuard({ target: globalThis.window,
  confirm: message => globalThis.window.confirm(message) })
export const registerUnsavedChanges = (read, scope) => shared.register(read, scope)
export const confirmUnsavedLeave = scope => shared.confirmLeave(scope)
export const runAfterUnsavedConfirmation = (action, options) => shared.run(action, options)

// Hash changes also cover the browser's Back/Forward buttons. A cancelled
// transition restores the URL without unmounting the current form or adding
// another history entry. Opening a new tab never changes this window's hash.
export function installGuardedHashNavigation({ target, resolvePage, initialPage, commitPage,
  confirmLeave = confirmUnsavedLeave }) {
  let currentPage = initialPage
  const change = () => {
    const nextPage = resolvePage()
    if (nextPage === currentPage) return
    if (!confirmLeave()) {
      target.history.replaceState(target.history.state, '',
        `${target.location.pathname}${target.location.search}#/${currentPage}`)
      return
    }
    currentPage = nextPage
    commitPage(nextPage)
  }
  target.addEventListener('hashchange', change)
  return () => target.removeEventListener('hashchange', change)
}
