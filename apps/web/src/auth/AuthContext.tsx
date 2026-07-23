import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  loginAsGuest as loginAsGuestRequest,
  type AuthUser,
} from '../api'
import { LoginPage } from './LoginPage'

type AuthContextValue = {
  user: AuthUser | null
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  loginAsGuest: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    void getCurrentUser()
      .then((current) => {
        if (active) setUser(current)
      })
      .catch(() => {
        if (active) setUser(null)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    const unauthorized = () => setUser(null)
    window.addEventListener('tp:unauthorized', unauthorized)
    return () => {
      active = false
      window.removeEventListener('tp:unauthorized', unauthorized)
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAdmin: user?.role === 'admin',
      login: async (username, password) => {
        setUser(await loginRequest(username, password))
      },
      logout: async () => {
        try {
          await logoutRequest()
        } finally {
          setUser(null)
        }
      },
      loginAsGuest: async () => {
        setUser(await loginAsGuestRequest())
      },
    }),
    [user],
  )

  return (
    <AuthContext.Provider value={value}>
      {loading ? (
        <div className="auth-loading">Loading Test Platform…</div>
      ) : user ? (
        children
      ) : (
        <LoginPage />
      )}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
