import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import http, { api, setAuthToken } from './api'
const AuthContext = createContext(null)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const clear = useCallback(() => {
    setUser(null); setAuthToken(null)
    try { localStorage.removeItem('hrts.auth') } catch {}
  }, [])
  const logout = useCallback(async () => {
    try { await api.logout() } finally { clear() }
  }, [clear])
  const login = useCallback(async (username, password) => {
    const { data } = await api.login(username, password)
    setUser({ username: data.username, role: data.role, displayName: data.display_name })
  }, [])
  useEffect(() => {
    clear()
    let active = true
    api.me().then(({ data }) => {
      if (active) setUser({ ...data, displayName: data.display_name })
    }).catch(() => {}).finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [clear])
  useEffect(() => {
    const id = http.interceptors.response.use(r => r, error => {
      if (error.response?.status === 401) clear()
      return Promise.reject(error)
    })
    return () => http.interceptors.response.eject(id)
  }, [clear])
  return <AuthContext.Provider value={{ user, session: user, isAdmin: user?.role === 'admin',
    isAuthenticated: Boolean(user), checking, login, logout }}>{children}</AuthContext.Provider>
}
export function useAuth() { return useContext(AuthContext) }
