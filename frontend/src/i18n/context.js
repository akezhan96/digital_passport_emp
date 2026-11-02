import { createContext } from 'react'

// Keep the context identity stable when Vite refreshes dictionaries/providers.
// Otherwise an existing provider and a refreshed hook can use different contexts.
export const I18nContext = createContext(null)
