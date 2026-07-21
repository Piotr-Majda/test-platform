import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AppShell } from './layout/AppShell'
import { NavStackProvider } from './navigation/NavStack'
import { HistoryPage } from './pages/HistoryPage'
import { ScenarioConfigPage } from './pages/ScenarioConfigPage'
import { ScenarioPage } from './pages/ScenarioPage'
import { ScenariosPage } from './pages/ScenariosPage'
import { TestDetailPage } from './pages/TestDetailPage'
import './App.css'
import { useAuth } from './auth/AuthContext'

function AdminOnly({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth()
  return isAdmin ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <NavStackProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<ScenariosPage />} />
            <Route
              path="scenarios/new"
              element={<AdminOnly><ScenarioConfigPage mode="new" /></AdminOnly>}
            />
            <Route
              path="scenarios/:scenarioId/runs/:runId/tests/:testId"
              element={<TestDetailPage />}
            />
            <Route path="scenarios/:scenarioId" element={<ScenarioPage />} />
            <Route
              path="scenarios/:scenarioId/configure"
              element={<AdminOnly><ScenarioConfigPage mode="edit" /></AdminOnly>}
            />
            <Route path="scenarios/:scenarioId/history" element={<HistoryPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </NavStackProvider>
    </BrowserRouter>
  )
}
