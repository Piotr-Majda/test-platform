import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useNavStack } from '../navigation/NavStack'
import { AppShellFrame } from './SubHeader'

export function AppShell() {
  const { back, canBack } = useNavStack()
  const location = useLocation()
  const showBack = canBack || location.pathname !== '/'

  return (
    <AppShellFrame
      header={
        <header className="app-header">
          <div className="app-header-brand">
            <NavLink to="/" className="brand-link" end>
              Test Platform
            </NavLink>
          </div>
          <nav className="app-nav" aria-label="Main">
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              Scenarios
            </NavLink>
            <NavLink
              to="/scenarios/new"
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              New scenario
            </NavLink>
          </nav>
          <div className="app-header-actions">
            {showBack ? (
              <button type="button" className="ghost" onClick={() => back('/')}>
                Back
              </button>
            ) : null}
          </div>
        </header>
      }
    >
      <Outlet />
    </AppShellFrame>
  )
}
