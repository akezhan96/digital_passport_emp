import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import http, { api, setAuthToken } from './api'

const AuthContext = createContext(null)
const STORAGE_KEY = 'hrts.auth'

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(readStored)
  const [checking, setChecking] = useState(Boolean(readStored()))

  // Push the stored token into the HTTP client before any request goes out.
  if (session?.token) setAuthToken(session.token)

  const logout = useCallback(() => {
    setSession(null)
    setAuthToken(null)
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
  }, [])

  const login = useCallback(async (username, password) => {
    const r = await api.login(username, password)
    const next = {
      token: r.data.token,
      username: r.data.username,
      role: r.data.role,
      displayName: r.data.display_name,
    }
    setAuthToken(next.token)
    setSession(next)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch { /* ignore */ }
    return next
  }, [])

  // A stored token may have expired while the tab was closed.
  useEffect(() => {
    if (!session?.token) { setChecking(false); return }
    let cancelled = false
    api.me()
      .then(() => { if (!cancelled) setChecking(false) })
      .catch(() => { if (!cancelled) { logout(); setChecking(false) } })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Any 401 from anywhere means the session is gone; drop it once.
  useEffect(() => {
    const id = http.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err?.response?.status === 401) logout()
        return Promise.reject(err)
      },
    )
    return () => http.interceptors.response.eject(id)
  }, [logout])

  return (
    <AuthContext.Provider value={{
      session,
      user: session,
      isAdmin: session?.role === 'admin',
      isAuthenticated: Boolean(session?.token),
      checking,
      login,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
