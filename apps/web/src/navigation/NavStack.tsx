import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

type NavStackValue = {
  go: (to: string) => void
  back: (fallback?: string) => void
  cancelTo: (to?: string) => void
  canBack: boolean
}

const NavStackContext = createContext<NavStackValue | null>(null)

export function NavStackProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [stack, setStack] = useState<string[]>([])
  const currentKey = `${location.pathname}${location.search}`

  const go = useCallback(
    (to: string) => {
      setStack((prev) => [...prev, currentKey])
      navigate(to)
    },
    [currentKey, navigate],
  )

  const back = useCallback(
    (fallback = '/') => {
      const prevPath = stack[stack.length - 1]
      setStack((prev) => prev.slice(0, -1))
      navigate(prevPath ?? fallback)
    },
    [navigate, stack],
  )

  const cancelTo = useCallback(
    (to = '/') => {
      navigate(to)
    },
    [navigate],
  )

  const value = useMemo(
    () => ({ go, back, cancelTo, canBack: stack.length > 0 }),
    [go, back, cancelTo, stack.length],
  )

  return <NavStackContext.Provider value={value}>{children}</NavStackContext.Provider>
}

export function useNavStack(): NavStackValue {
  const ctx = useContext(NavStackContext)
  if (!ctx) throw new Error('useNavStack must be used within NavStackProvider')
  return ctx
}
