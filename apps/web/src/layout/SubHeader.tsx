import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { Outlet } from 'react-router-dom'

type SubHeaderContextValue = {
  setSubHeader: (node: ReactNode) => void
}

const SubHeaderContext = createContext<SubHeaderContextValue | null>(null)

export function useSubHeaderSlot(): SubHeaderContextValue {
  const ctx = useContext(SubHeaderContext)
  if (!ctx) throw new Error('useSubHeaderSlot must be used within AppShell')
  return ctx
}

export function AppShellFrame({
  header,
  children,
}: {
  header: ReactNode
  children?: ReactNode
}) {
  const [subHeader, setSubHeader] = useState<ReactNode>(null)
  const value = useMemo(() => ({ setSubHeader }), [])

  return (
    <SubHeaderContext.Provider value={value}>
      <div className="app-shell">
        {header}
        {subHeader ? <div className="app-subheader">{subHeader}</div> : null}
        <main className="app-main">{children ?? <Outlet />}</main>
      </div>
    </SubHeaderContext.Provider>
  )
}
