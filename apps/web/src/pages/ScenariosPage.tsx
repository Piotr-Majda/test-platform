import { useCallback, useEffect, useState } from 'react'
import {
  deleteScenario,
  getRun,
  getScenarioHistory,
  listScenarios,
  startRun,
  type Scenario,
} from '../api'
import { formatDateTime, formatMs } from '../lib/format'
import { PageSubHeader } from '../layout/PageSubHeader'
import { useNavStack } from '../navigation/NavStack'
import { useAuth } from '../auth/AuthContext'

type Row = {
  scenario: Scenario
  lastStatus: string | null
  lastDurationMs: number | null
  lastAt: string | null
  activeRunId: string | null
}

export function ScenariosPage() {
  const { isAdmin } = useAuth()
  const { go } = useNavStack()
  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runAllBusy, setRunAllBusy] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [runAllNote, setRunAllNote] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const scenarios = await listScenarios()
      const enriched = await Promise.all(
        scenarios.map(async (scenario) => {
          try {
            const history = await getScenarioHistory(scenario.id)
            const last = history.runs[0] ?? null
            const inFlight =
              last && last.status !== 'finished' && last.status !== 'failed' ? last.id : null
            return {
              scenario,
              lastStatus: last?.status ?? null,
              lastDurationMs: last?.duration_ms ?? null,
              lastAt: last?.created_at ?? null,
              activeRunId: inFlight,
            } satisfies Row
          } catch {
            return {
              scenario,
              lastStatus: null,
              lastDurationMs: null,
              lastAt: null,
              activeRunId: null,
            } satisfies Row
          }
        }),
      )
      setRows(enriched)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenarios')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll in-flight runs so landing shows current status without navigating away.
  const activeKey = rows
    .filter((r) => r.activeRunId)
    .map((r) => `${r.scenario.id}:${r.activeRunId}`)
    .join(',')

  useEffect(() => {
    if (!activeKey) return
    const snapshot = activeKey.split(',').map((pair) => {
      const [scenarioId, runId] = pair.split(':')
      return { scenarioId, runId }
    })
    const timer = window.setInterval(() => {
      void Promise.all(
        snapshot.map(async ({ scenarioId, runId }) => {
          try {
            return { scenarioId, run: await getRun(runId) }
          } catch {
            return null
          }
        }),
      ).then((updates) => {
        setRows((current) =>
          current.map((row) => {
            const hit = updates.find((u) => u && u.scenarioId === row.scenario.id)
            if (!hit) return row
            const done = hit.run.status === 'finished' || hit.run.status === 'failed'
            return {
              ...row,
              lastStatus: hit.run.status,
              lastDurationMs: hit.run.duration_ms ?? hit.run.projection.scenario_duration_ms,
              activeRunId: done ? null : hit.run.id,
            }
          }),
        )
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [activeKey])

  const remove = async (scenarioId: string) => {
    setBusy(true)
    try {
      await deleteScenario(scenarioId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    } finally {
      setBusy(false)
    }
  }

  const runOne = async (scenarioId: string) => {
    setRunningId(scenarioId)
    setError(null)
    try {
      const started = await startRun(scenarioId)
      setRows((prev) =>
        prev.map((row) =>
          row.scenario.id === scenarioId
            ? {
                ...row,
                lastStatus: 'queued',
                lastDurationMs: null,
                lastAt: new Date().toISOString(),
                activeRunId: started.id,
              }
            : row,
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setRunningId(null)
    }
  }

  const runAllParallel = async () => {
    if (rows.length === 0) return
    setRunAllBusy(true)
    setRunAllNote(null)
    setError(null)
    try {
      const results = await Promise.allSettled(rows.map((row) => startRun(row.scenario.id)))
      const ok = results.filter((r) => r.status === 'fulfilled').length
      const failed = results.length - ok
      setRunAllNote(
        failed === 0
          ? `Started ${ok} scenario run(s).`
          : `Started ${ok} run(s); ${failed} failed to queue.`,
      )
      setRows((prev) =>
        prev.map((row, index) => {
          const result = results[index]
          if (result.status !== 'fulfilled') return row
          return {
            ...row,
            lastStatus: 'queued',
            lastDurationMs: null,
            lastAt: new Date().toISOString(),
            activeRunId: result.value.id,
          }
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run all')
    } finally {
      setRunAllBusy(false)
    }
  }

  const actionsDisabled = busy || runAllBusy || runningId != null

  return (
    <div className="page">
      <PageSubHeader>
        <div className="page-subhead-inner">
          <div>
            <h1>Scenarios</h1>
            <p className="lede tight">Open, configure, or run. Buttons only — card text does nothing.</p>
          </div>
          <div className="row-actions">
            <button
              type="button"
              className="primary"
              disabled={actionsDisabled || rows.length === 0}
              onClick={() => void runAllParallel()}
            >
              {runAllBusy ? 'Starting all…' : 'Run all'}
            </button>
            <button
              type="button"
              className="ghost"
              disabled={actionsDisabled || !isAdmin}
              title={isAdmin ? undefined : 'Admin role required'}
              onClick={() => go('/scenarios/new')}
            >
              New scenario
            </button>
          </div>
        </div>
      </PageSubHeader>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {runAllNote ? <p className="muted tight">{runAllNote}</p> : null}

      {rows.length === 0 ? (
        <section className="panel">
          <p className="muted">No scenarios yet. Create one to get started.</p>
          {isAdmin ? (
            <button type="button" className="primary" onClick={() => go('/scenarios/new')}>
              New scenario
            </button>
          ) : null}
        </section>
      ) : (
        <ul className="scenario-list landing-list">
          {rows.map(({ scenario, lastStatus, lastDurationMs, lastAt, activeRunId }) => (
            <li key={scenario.id}>
              <div className="scenario-card-static">
                <strong>{scenario.name}</strong>
                <small>
                  {scenario.test_ids.join(' → ') || 'no tests'} · SUT {scenario.sut_version}
                </small>
                <span className="landing-status">
                  {lastStatus ? (
                    <>
                      <span
                        className={`status status-${
                          lastStatus === 'failed'
                            ? 'failed'
                            : lastStatus === 'finished'
                              ? 'finished'
                              : lastStatus === 'running'
                                ? 'running'
                                : 'queued'
                        }`}
                      >
                        {lastStatus}
                      </span>
                      <span className="muted">
                        {formatMs(lastDurationMs)}
                        {lastAt ? ` · ${formatDateTime(lastAt)}` : ''}
                        {activeRunId ? ' · live' : ' · last run'}
                      </span>
                    </>
                  ) : (
                    <span className="muted">Never run</span>
                  )}
                </span>
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={actionsDisabled}
                  onClick={() => void runOne(scenario.id)}
                >
                  {runningId === scenario.id ? 'Starting…' : 'Run'}
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={actionsDisabled}
                  onClick={() => go(`/scenarios/${scenario.id}`)}
                >
                  Open
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={actionsDisabled}
                  onClick={() => go(`/scenarios/${scenario.id}/history`)}
                >
                  History
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={actionsDisabled || !isAdmin}
                  title={isAdmin ? undefined : 'Admin role required'}
                  onClick={() => go(`/scenarios/${scenario.id}/configure`)}
                >
                  Configure
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={actionsDisabled || !isAdmin}
                  title={isAdmin ? undefined : 'Admin role required'}
                  onClick={() => void remove(scenario.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
