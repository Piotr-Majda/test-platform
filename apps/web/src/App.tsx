import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layout/AppShell'
import { NavStackProvider } from './navigation/NavStack'
import { HistoryPage } from './pages/HistoryPage'
import { ScenarioConfigPage } from './pages/ScenarioConfigPage'
import { ScenarioPage } from './pages/ScenarioPage'
import { ScenariosPage } from './pages/ScenariosPage'
import { TestDetailPage } from './pages/TestDetailPage'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <NavStackProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<ScenariosPage />} />
            <Route path="scenarios/new" element={<ScenarioConfigPage mode="new" />} />
            <Route
              path="scenarios/:scenarioId/runs/:runId/tests/:testId"
              element={<TestDetailPage />}
            />
            <Route path="scenarios/:scenarioId" element={<ScenarioPage />} />
            <Route path="scenarios/:scenarioId/configure" element={<ScenarioConfigPage mode="edit" />} />
            <Route path="scenarios/:scenarioId/history" element={<HistoryPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </NavStackProvider>
    </BrowserRouter>
  )
}
