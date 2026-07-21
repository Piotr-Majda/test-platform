import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  artifactUrl,
  cacheRunAnalysis,
  fetchLogDocument,
  fetchTestLogForRun,
  getAnalysis,
  getRun,
  getScenarioHistory,
  listScenarios,
  readCachedRunAnalysis,
  runAnalysisAndWait,
  startRun,
  tryGetRunAnalysis,
  type AnalysisReport,
  type ArtifactRef,
  type LogDocument,
  type RunDetail,
  type Scenario,
  type ScenarioHistory,
  type StepView,
} from '../api'
import { AnalysisPanel } from '../components/AnalysisPanel'
import { AnalysisSpinner, IconAnalyzed, IconNotAnalyzed } from '../components/AnalysisStateIcon'
import { RunMetaLine, resolveRunDurationMs } from '../components/RunMetaLine'
import { StepLogViewer } from '../components/StepLogViewer'
import { formatDateTime, formatMs, groupStepsByTest } from '../lib/format'
import { PageSubHeader } from '../layout/PageSubHeader'
import { useNavStack } from '../navigation/NavStack'
import { useAuth } from '../auth/AuthContext'

export function ScenarioPage() {
  const { isAdmin } = useAuth()
  const { scenarioId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { go, back } = useNavStack()
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [history, setHistory] = useState<ScenarioHistory | null>(null)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null)
  const [testAnalysisIds, setTestAnalysisIds] = useState<Record<string, string>>({})
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [logTitle, setLogTitle] = useState('')
  const [logDocument, setLogDocument] = useState<LogDocument | null>(null)
  const [logError, setLogError] = useState<string | null>(null)
  const [logDownloadUrl, setLogDownloadUrl] = useState<string | null>(null)
  const logViewRef = useRef<HTMLElement | null>(null)
  const analysisViewRef = useRef<HTMLElement | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())

  const load = useCallback(async () => {
    if (!scenarioId) return
    setError(null)
    try {
      const [all, hist] = await Promise.all([listScenarios(), getScenarioHistory(scenarioId)])
      setScenario(all.find((s) => s.id === scenarioId) ?? null)
      setHistory(hist)
      return hist
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenario')
      return null
    }
  }, [scenarioId])

  useEffect(() => {
    let cancelled = false
    const openingSpecific = Boolean(searchParams.get('run'))
    void (async () => {
      const hist = await load()
      if (cancelled || !hist) return
      if (openingSpecific) return
      const latestId = hist.runs[0]?.id
      if (!latestId) return
      try {
        const detail = await getRun(latestId)
        if (cancelled) return
        setRun(detail)
        setExpandedErrors(new Set())
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to open run')
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // Intentionally ignore searchParams: ?run= is handled by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, load])

  const queryRunId = searchParams.get('run')
  useEffect(() => {
    if (!queryRunId) return
    let cancelled = false
    void (async () => {
      try {
        const detail = await getRun(queryRunId)
        if (cancelled) return
        setRun(detail)
        setExpandedErrors(new Set())
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams()
            const from = prev.get('from')
            if (from) next.set('from', from)
            return next
          },
          { replace: true },
        )
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to open run')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [queryRunId, setSearchParams])

  useEffect(() => {
    if (!run || run.status === 'finished' || run.status === 'failed') {
      if (run && (run.status === 'finished' || run.status === 'failed')) {
        void load()
      }
      return
    }
    const timer = window.setInterval(() => {
      void getRun(run.id)
        .then(setRun)
        .catch((err) => setError(err instanceof Error ? err.message : 'Poll failed'))
      setNowMs(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [run, load])

  useEffect(() => {
    if (!run?.id) return
    let cancelled = false
    void (async () => {
      const cached = readCachedRunAnalysis(run.id)
      if (cached && !cancelled) {
        if (cached.run) setAnalysis(cached.run)
        const map: Record<string, string> = {}
        for (const [tid, report] of Object.entries(cached.tests ?? {})) map[tid] = report.id
        for (const ref of cached.run?.test_analyses ?? []) {
          if (ref.test_id && !map[ref.test_id]) map[ref.test_id] = ref.analysis_id
        }
        setTestAnalysisIds(map)
      }
      const bundle = await tryGetRunAnalysis(run.id)
      if (cancelled || !bundle) return
      cacheRunAnalysis(run.id, bundle)
      if (bundle.run) setAnalysis(bundle.run)
      const map: Record<string, string> = {}
      for (const [tid, report] of Object.entries(bundle.tests ?? {})) map[tid] = report.id
      for (const ref of bundle.run?.test_analyses ?? []) {
        if (ref.test_id && !map[ref.test_id]) map[ref.test_id] = ref.analysis_id
      }
      setTestAnalysisIds(map)
    })()
    return () => {
      cancelled = true
    }
  }, [run?.id])

  const runScenario = async () => {
    if (!scenarioId) return
    setBusy(true)
    setError(null)
    setAnalysis(null)
    setTestAnalysisIds({})
    setAnalysisError(null)
    try {
      const started = await startRun(scenarioId)
      setExpandedErrors(new Set())
      setNowMs(Date.now())
      setRun(await getRun(started.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setBusy(false)
    }
  }

  const openHistoryRun = async (runId: string) => {
    setBusy(true)
    try {
      setRun(await getRun(runId))
      setExpandedErrors(new Set())
      setLogOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open run')
    } finally {
      setBusy(false)
    }
  }

  const analyzeThisRun = async () => {
    if (!run) return
    setAnalysisLoading(true)
    setAnalysisError(null)
    window.requestAnimationFrame(() => {
      analysisViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    try {
      const report = await runAnalysisAndWait({ scope: 'run', run_id: run.id })
      setAnalysis(report)
      const map: Record<string, string> = {}
      for (const ref of report.test_analyses ?? []) {
        map[ref.test_id] = ref.analysis_id
      }
      setTestAnalysisIds(map)

      // Hydrate per-test reports via /analyses/{id} (always available) + optional bundle endpoint
      const tests: Record<string, AnalysisReport> = {}
      await Promise.all(
        (report.test_analyses ?? []).map(async (ref) => {
          try {
            tests[ref.test_id] = await getAnalysis(ref.analysis_id)
          } catch {
            /* child may still be loading; Detail can retry */
          }
        }),
      )
      const bundle = await tryGetRunAnalysis(run.id)
      for (const [tid, child] of Object.entries(bundle?.tests ?? {})) {
        tests[tid] = child
        map[tid] = child.id
      }
      cacheRunAnalysis(run.id, { run: bundle?.run ?? report, tests })
      if (bundle?.run) setAnalysis(bundle.run)
      setTestAnalysisIds({ ...map })
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setAnalysisLoading(false)
    }
  }

  const openLogPath = async (title: string, relativePath: string) => {
    setLogOpen(true)
    setLogTitle(title)
    setLogDocument(null)
    setLogError(null)
    setLogDownloadUrl(artifactUrl(relativePath))
    window.requestAnimationFrame(() => {
      logViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    try {
      setLogDocument(await fetchLogDocument(relativePath))
    } catch (err) {
      setLogError(err instanceof Error ? err.message : 'Failed to load log')
    }
  }

  const openStepLog = (stepName: string, artifact: ArtifactRef) => {
    void openLogPath(`${stepName} · ${artifact.name}`, artifact.relative_path)
  }

  const openTestLog = (runId: string, testId?: string | null, steps?: StepView[]) => {
    const label = testId ? `Test ${testId}` : 'Test log'
    setLogOpen(true)
    setLogTitle(`${label} · logs`)
    setLogDocument(null)
    setLogError(null)
    setLogDownloadUrl(null)
    window.requestAnimationFrame(() => {
      logViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    void fetchTestLogForRun(runId, testId, steps ?? run?.projection.steps ?? [])
      .then(({ document, downloadUrl }) => {
        setLogDocument(document)
        setLogDownloadUrl(downloadUrl)
      })
      .catch((err) => setLogError(err instanceof Error ? err.message : 'Failed to load log'))
  }

  const toggleErrorExpand = (key: string) => {
    setExpandedErrors((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (!scenario && !error) {
    return (
      <div className="page">
        <p className="muted">Loading scenario…</p>
      </div>
    )
  }

  if (!scenario) {
    return (
      <div className="page">
        <p className="error">{error ?? 'Scenario not found'}</p>
        <button type="button" className="ghost" onClick={() => back('/')}>
          Back
        </button>
      </div>
    )
  }

  const statusLabel = run?.status ?? history?.runs[0]?.status ?? 'idle'
  const runWhenLabel = run?.created_at ? formatDateTime(run.created_at) : null
  const liveDurationMs = resolveRunDurationMs(run, nowMs)
  const fromOrigin = searchParams.get('from') === 'history' ? 'history' : 'scenario'
  const testDetailHref = (testId: string) =>
    run
      ? `/scenarios/${scenario.id}/runs/${run.id}/tests/${encodeURIComponent(testId)}?from=${fromOrigin}`
      : '#'

  return (
    <div className="page scenario-page">
      <PageSubHeader>
        <div className="page-subhead-inner sticky-run-bar-inner">
          <div className="sticky-run-main">
            <div>
              <h1>{scenario.name}</h1>
              <p className="muted tight">
                {scenario.test_ids.join(' → ')} · SUT {scenario.sut_version}
              </p>
            </div>
            <div className="sticky-run-status">
              <span
                className={`status ${
                  statusLabel === 'failed'
                    ? 'status-failed'
                    : statusLabel === 'idle'
                      ? 'status-idle'
                      : `status-${statusLabel}`
                }`}
              >
                {statusLabel}
              </span>
              {run ? (
                <span className="muted">
                  {runWhenLabel ? `${runWhenLabel} · ` : ''}
                  {formatMs(liveDurationMs)} · run <code>{run.id}</code>
                </span>
              ) : (
                <span className="muted">No runs yet</span>
              )}
            </div>
          </div>
          <div className="sticky-run-actions">
            <button type="button" className="primary" disabled={busy} onClick={() => void runScenario()}>
              {busy ? 'Starting…' : 'Run'}
            </button>
            <button
              type="button"
              className="ghost"
              disabled={analysisLoading || !run}
              onClick={() => void analyzeThisRun()}
            >
              {analysisLoading ? 'Analyzing…' : 'Analyze this run'}
            </button>
            <button type="button" className="ghost" onClick={() => go(`/scenarios/${scenario.id}/history`)}>
              History
            </button>
            <button
              type="button"
              className="ghost"
              disabled={!isAdmin}
              title={isAdmin ? undefined : 'Admin role required'}
              onClick={() => go(`/scenarios/${scenario.id}/configure`)}
            >
              Configure
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() =>
                fromOrigin === 'history'
                  ? back(`/scenarios/${scenario.id}/history`)
                  : back('/')
              }
            >
              Back
            </button>
          </div>
        </div>
      </PageSubHeader>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <section className="panel wide" aria-labelledby="run-view">
        <h2 id="run-view">Tests & status</h2>
        {run ? (
          <>
            <RunMetaLine
              runId={run.id}
              status={run.status}
              createdAt={run.created_at}
              durationMs={liveDurationMs}
              extra={`SUT ${run.sut_version} · FW ${run.framework_version}`}
            />

            <div className="test-blocks">
              {run.projection.steps.length === 0 ? (
                <div className="totals">
                  <h3>Tests in this run</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>Test</th>
                        <th>Status</th>
                        <th>Time</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(run.projection.tests.length > 0
                        ? run.projection.tests
                        : scenario.test_ids.map((id) => ({
                            test_id: id,
                            status: 'not run',
                            duration_ms: null as number | null,
                          }))
                      ).map((test) => (
                        <tr key={test.test_id}>
                          <td>
                            <span className="test-meta-title">
                              {analysisLoading ? (
                                <AnalysisSpinner />
                              ) : testAnalysisIds[test.test_id] ? (
                                <IconAnalyzed />
                              ) : (
                                <IconNotAnalyzed />
                              )}
                              {test.test_id}
                            </span>
                          </td>
                          <td>{test.status}</td>
                          <td>{formatMs(test.duration_ms)}</td>
                          <td>
                            <Link
                              className="ghost button-link"
                              to={testDetailHref(test.test_id)}
                              onClick={(event) => {
                                event.preventDefault()
                                go(testDetailHref(test.test_id))
                              }}
                            >
                              Detail
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted tight">Waiting for step results…</p>
                </div>
              ) : (
                groupStepsByTest(run.projection.steps, run.projection.tests).map((group) => {
                  const testMeta = run.projection.tests.find((t) => t.test_id === group.testId)
                  return (
                    <div key={group.testId ?? 'ungrouped'} className="test-block">
                      <table className="data-table steps-table">
                        <thead>
                          <tr>
                            <th>Step</th>
                            <th>Status</th>
                            <th>Time</th>
                            <th>Error</th>
                            <th>Logs</th>
                            <th>Artifacts / Detail</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="test-meta-row">
                            <td>
                              <span className="test-meta-title">
                                {analysisLoading ? (
                                  <AnalysisSpinner />
                                ) : group.testId && testAnalysisIds[group.testId] ? (
                                  <IconAnalyzed />
                                ) : (
                                  <IconNotAnalyzed />
                                )}
                                <strong>{group.testId ?? 'Ungrouped steps'}</strong>
                              </span>
                            </td>
                            <td
                              className={
                                testMeta ? `cell-${testMeta.status === 'success' ? 'success' : 'failed'}` : ''
                              }
                            >
                              {testMeta?.status ?? '—'}
                            </td>
                            <td>{formatMs(testMeta?.duration_ms ?? null)}</td>
                            <td>—</td>
                            <td>
                              <button
                                type="button"
                                className="ghost artifact-open"
                                disabled={busy || !group.testId}
                                onClick={() => openTestLog(run.id, group.testId, group.steps)}
                              >
                                Open test logs
                              </button>
                            </td>
                            <td>
                              {group.testId ? (
                                <Link
                                  className="ghost button-link"
                                  to={testDetailHref(group.testId)}
                                  onClick={(event) => {
                                    event.preventDefault()
                                    go(testDetailHref(group.testId!))
                                  }}
                                >
                                  Detail
                                </Link>
                              ) : (
                                '—'
                              )}
                            </td>
                          </tr>
                          {group.steps.map((step, index) => {
                            const errorKey = `${run.id}-${group.testId}-${step.name}-${index}`
                            const expanded = expandedErrors.has(errorKey)
                            const logArts = step.artifacts.filter(
                              (a) =>
                                a.name !== 'test.log.json' &&
                                (a.kind === 'log' ||
                                  a.name.endsWith('.log.json') ||
                                  a.name.includes('log.json')),
                            )
                            const otherArts = step.artifacts.filter(
                              (a) =>
                                a.name !== 'test.log.json' &&
                                !(
                                  a.kind === 'log' ||
                                  a.name.endsWith('.log.json') ||
                                  a.name.includes('log.json')
                                ),
                            )
                            return (
                              <tr key={errorKey}>
                                <td>{step.name}</td>
                                <td className={`cell-${step.status}`}>{step.status}</td>
                                <td>{formatMs(step.duration_ms)}</td>
                                <td className="col-error">
                                  {step.error_message || step.error_trace ? (
                                    <>
                                      <span className="error-short" title={step.error_message ?? undefined}>
                                        {step.error_message ?? 'Error'}
                                      </span>
                                      {step.error_trace ? (
                                        <button
                                          type="button"
                                          className="ghost expand-error"
                                          onClick={() => toggleErrorExpand(errorKey)}
                                        >
                                          {expanded ? 'Hide' : 'Expand'}
                                        </button>
                                      ) : null}
                                      {expanded && step.error_trace ? (
                                        <pre className="error-trace">{step.error_trace}</pre>
                                      ) : null}
                                    </>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                                <td className="col-artifacts">
                                  {logArts.length === 0
                                    ? '—'
                                    : logArts.map((artifact) => (
                                        <button
                                          key={artifact.id}
                                          type="button"
                                          className="ghost artifact-open"
                                          disabled={busy}
                                          onClick={() => void openStepLog(step.name, artifact)}
                                        >
                                          {artifact.name}
                                        </button>
                                      ))}
                                </td>
                                <td className="col-artifacts">
                                  {otherArts.length === 0
                                    ? '—'
                                    : otherArts.map((artifact) => (
                                        <a
                                          key={artifact.id}
                                          href={artifactUrl(artifact.relative_path)}
                                          download={artifact.name}
                                        >
                                          {artifact.name}
                                        </a>
                                      ))}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )
                })
              )}
            </div>
          </>
        ) : (
          <div className="totals">
            <h3>Tests in scenario</h3>
            <table>
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {scenario.test_ids.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="muted">
                      No tests configured.
                    </td>
                  </tr>
                ) : (
                  scenario.test_ids.map((id) => (
                    <tr key={id}>
                      <td>{id}</td>
                      <td>not run</td>
                      <td>—</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            <p className="muted tight">Run the scenario to see live step status, logs, and artifacts.</p>
          </div>
        )}
      </section>

      {run ? (
        <section ref={analysisViewRef} className="panel wide" aria-labelledby="analysis-view">
          <h2 id="analysis-view">Run analysis</h2>
          <RunMetaLine
            runId={run.id}
            status={run.status}
            createdAt={run.created_at}
            durationMs={liveDurationMs}
          />
          {analysisLoading ? (
            <p className="muted">Analyzing…</p>
          ) : (
            <>
              {analysisError ? <p className="error">{analysisError}</p> : null}
              <AnalysisPanel
                report={analysis}
                busy={busy}
                onOpenRun={(id) => void openHistoryRun(id)}
                emptyHint="Not analyzed yet — click Analyze this run in the header. Results are saved and restored when you come back."
              />
            </>
          )}
        </section>
      ) : null}

      {logOpen ? (
        <section ref={logViewRef} className="panel wide" aria-labelledby="log-view">
          <h2 id="log-view">Logs</h2>
          <StepLogViewer
            title={logTitle}
            document={logDocument}
            error={logError}
            downloadUrl={logDownloadUrl}
            onClose={() => {
              setLogOpen(false)
              setLogDocument(null)
              setLogError(null)
              setLogTitle('')
              setLogDownloadUrl(null)
            }}
          />
        </section>
      ) : null}
    </div>
  )
}
