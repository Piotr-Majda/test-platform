import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useNavStack } from '../navigation/NavStack'
import { AppShellFrame } from './SubHeader'
import { useAuth } from '../auth/AuthContext'

export function AppShell() {
  const { user, isAdmin, logout } = useAuth()
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
            {isAdmin ? (
              <NavLink
                to="/scenarios/new"
                className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
              >
                New scenario
              </NavLink>
            ) : (
              <span className="nav-link disabled" title="Admin role required" aria-disabled="true">
                New scenario
              </span>
            )}
          </nav>
          <div className="app-header-actions">
            <span className={`role-badge role-${user!.role}`}>{user!.role}</span>
            {showBack ? (
              <button type="button" className="ghost" onClick={() => back('/')}>
                Back
              </button>
            ) : null}
            <button type="button" className="ghost" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        </header>
      }
    >
      <Outlet />
    </AppShellFrame>
  )
}
