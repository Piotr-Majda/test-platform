import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  analysisExportUrl,
  artifactUrl,
  fetchLogDocument,
  fetchTestLogForRun,
  getAnalysis,
  getRun,
  listScenarios,
  readCachedRunAnalysis,
  runAnalysisAndWait,
  tryGetRunAnalysis,
  tryGetTestAnalysis,
  cacheRunAnalysis,
  type AnalysisReport,
  type ArtifactRef,
  type LogDocument,
  type RunDetail,
  type Scenario,
  type StepView,
} from '../api'
import { AnalysisPanel } from '../components/AnalysisPanel'
import { AnalysisSpinner, IconAnalyzed, IconNotAnalyzed } from '../components/AnalysisStateIcon'
import { RunMetaLine, resolveRunDurationMs } from '../components/RunMetaLine'
import { StepLogViewer } from '../components/StepLogViewer'
import { formatDateTime, formatMs, groupStepsByTest } from '../lib/format'
import { PageSubHeader } from '../layout/PageSubHeader'
import { useNavStack } from '../navigation/NavStack'

export function TestDetailPage() {
  const { scenarioId = '', runId = '', testId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const { go, back, cancelTo } = useNavStack()
  const from = searchParams.get('from') === 'history' ? 'history' : 'scenario'
  const backTarget =
    from === 'history'
      ? `/scenarios/${scenarioId}/history`
      : `/scenarios/${scenarioId}${runId ? `?run=${encodeURIComponent(runId)}` : ''}`
  const goBack = () => {
    if (from === 'history') cancelTo(backTarget)
    else back(backTarget)
  }
  const testDetailPath = (id: string) =>
    `/scenarios/${scenarioId}/runs/${runId}/tests/${encodeURIComponent(id)}?from=${from}`
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [logTitle, setLogTitle] = useState('')
  const [logDocument, setLogDocument] = useState<LogDocument | null>(null)
  const [logError, setLogError] = useState<string | null>(null)
  const [logDownloadUrl, setLogDownloadUrl] = useState<string | null>(null)
  const logViewRef = useRef<HTMLElement | null>(null)

  const load = useCallback(async () => {
    if (!scenarioId || !runId || !testId) return
    setError(null)
    try {
      const [all, detail] = await Promise.all([listScenarios(), getRun(runId)])
      setScenario(all.find((s) => s.id === scenarioId) ?? null)
      setRun(detail)

      const cached = readCachedRunAnalysis(runId)
      let found: AnalysisReport | null = cached?.tests?.[testId] ?? null
      if (!found) {
        const refId =
          cached?.run?.test_analyses?.find((item) => item.test_id === testId)?.analysis_id ?? null
        if (refId) {
          try {
            found = await getAnalysis(refId)
          } catch {
            found = null
          }
        }
      }
      if (!found) {
        found = await tryGetTestAnalysis(runId, testId)
      }
      if (!found) {
        const bundle = await tryGetRunAnalysis(runId)
        found = bundle?.tests?.[testId] ?? null
        if (!found) {
          const ref = bundle?.run?.test_analyses?.find((item) => item.test_id === testId)
          if (ref) {
            try {
              found = await getAnalysis(ref.analysis_id)
            } catch {
              found = null
            }
          }
        }
      }
      setReport(found)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load test')
    }
  }, [scenarioId, runId, testId])

  useEffect(() => {
    void load()
  }, [load])

  const analyzeTest = async () => {
    setAnalysisLoading(true)
    setAnalysisError(null)
    try {
      const result = await runAnalysisAndWait({
        scope: 'test',
        run_id: runId,
        test_id: testId,
        scenario_id: scenarioId,
      })
      setReport(result)
      const cached = readCachedRunAnalysis(runId) ?? { run: null, tests: {} }
      cacheRunAnalysis(runId, {
        run: cached.run,
        tests: { ...cached.tests, [testId]: result },
      })
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

  const openTestLog = (steps: StepView[]) => {
    setLogOpen(true)
    setLogTitle(`Test ${testId} · logs`)
    setLogDocument(null)
    setLogError(null)
    setLogDownloadUrl(null)
    window.requestAnimationFrame(() => {
      logViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    void fetchTestLogForRun(runId, testId, steps)
      .then(({ document, downloadUrl }) => {
        setLogDocument(document)
        setLogDownloadUrl(downloadUrl)
      })
      .catch((err) => setLogError(err instanceof Error ? err.message : 'Failed to load log'))
  }

  if (!scenario && !error) {
    return (
      <div className="page">
        <p className="muted">Loading test…</p>
      </div>
    )
  }

  if (!scenario || !run) {
    return (
      <div className="page">
        <p className="error">{error ?? 'Test or run not found'}</p>
        <button type="button" className="ghost" onClick={goBack}>
          Back
        </button>
      </div>
    )
  }

  const group = groupStepsByTest(run.projection.steps, run.projection.tests).find(
    (g) => g.testId === testId,
  )
  const testMeta = run.projection.tests.find((t) => t.test_id === testId)
  const suiteIds =
    run.projection.tests.length > 0 ? run.projection.tests.map((t) => t.test_id) : scenario.test_ids
  const liveDurationMs = resolveRunDurationMs(run, Date.now())
  const runWhenLabel = run.created_at ? formatDateTime(run.created_at) : null

  return (
    <div className="page">
      <PageSubHeader>
        <div className="page-subhead-inner">
          <div>
            <h1>
              {testId}{' '}
              <span className="analysis-state-inline" aria-hidden={false}>
                {analysisLoading ? (
                  <AnalysisSpinner />
                ) : report ? (
                  <IconAnalyzed />
                ) : (
                  <IconNotAnalyzed />
                )}
              </span>
            </h1>
            <p className="lede tight">
              {scenario.name} · {testMeta?.status ?? '—'} · {formatMs(testMeta?.duration_ms ?? null)}
            </p>
            <p className="muted tight">
              {runWhenLabel ? `${runWhenLabel} · ` : ''}
              run <code>{run.id}</code>
            </p>
          </div>
          <div className="row-actions">
            <button
              type="button"
              className="primary"
              disabled={analysisLoading}
              onClick={() => void analyzeTest()}
            >
              {analysisLoading ? 'Analyzing…' : 'Analyze this test'}
            </button>
            {report ? (
              <a className="ghost button-link" href={analysisExportUrl(report.id)} download>
                Download report
              </a>
            ) : null}
            <button type="button" className="ghost" onClick={goBack}>
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

      <section className="panel" aria-labelledby="suite-nav">
        <h2 id="suite-nav">Tests in this run</h2>
        <RunMetaLine
          runId={run.id}
          status={run.status}
          createdAt={run.created_at}
          durationMs={liveDurationMs}
        />
        <ul className="suite-test-list">
          {suiteIds.map((id) => (
            <li key={id}>
              <button
                type="button"
                className={id === testId ? 'ghost active-test' : 'ghost'}
                onClick={() => go(testDetailPath(id))}
              >
                {id}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel wide" aria-labelledby="test-steps">
        <div className="row-actions" style={{ marginBottom: '0.75rem' }}>
          <h2 id="test-steps" style={{ margin: 0, flex: 1 }}>
            Steps
          </h2>
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => {
              setBusy(true)
              openTestLog(group?.steps ?? [])
              setBusy(false)
            }}
          >
            Open test logs
          </button>
        </div>
        <RunMetaLine
          runId={run.id}
          status={testMeta?.status ?? run.status}
          createdAt={run.created_at}
          durationMs={testMeta?.duration_ms ?? liveDurationMs}
        />
        {!group || group.steps.length === 0 ? (
          <p className="muted">No steps recorded for this test in the run.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Test step results" tabIndex={0}>
            <table className="data-table steps-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>Status</th>
                <th>Time</th>
                <th>Error</th>
                <th>Logs</th>
                <th>Artifacts</th>
              </tr>
            </thead>
            <tbody>
              {group.steps.map((step, index) => {
                const logArts = step.artifacts.filter(
                  (a) =>
                    a.name !== 'test.log.json' &&
                    (a.kind === 'log' || a.name.endsWith('.log.json') || a.name.includes('log.json')),
                )
                const otherArts = step.artifacts.filter(
                  (a) =>
                    a.name !== 'test.log.json' &&
                    !(a.kind === 'log' || a.name.endsWith('.log.json') || a.name.includes('log.json')),
                )
                return (
                  <tr key={`${step.name}-${index}`}>
                    <td>{step.name}</td>
                    <td className={`cell-${step.status === 'success' ? 'success' : 'failed'}`}>
                      {step.status}
                    </td>
                    <td>{formatMs(step.duration_ms)}</td>
                    <td className="col-error">{step.error_message || '—'}</td>
                    <td className="col-artifacts">
                      {logArts.length === 0
                        ? '—'
                        : logArts.map((artifact) => (
                            <button
                              key={artifact.id}
                              type="button"
                              className="ghost artifact-open"
                              onClick={() => openStepLog(step.name, artifact)}
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
        )}
      </section>

      <section className="panel wide" aria-labelledby="test-analysis">
        <h2 id="test-analysis">Analysis</h2>
        <RunMetaLine
          runId={run.id}
          status={run.status}
          createdAt={run.created_at}
          durationMs={liveDurationMs}
          extra={`test ${testId}`}
        />
        {analysisLoading ? (
          <p className="muted">Analyzing…</p>
        ) : (
          <>
            {analysisError ? (
              <p className="error" role="alert">
                {analysisError}
              </p>
            ) : null}
            <AnalysisPanel
              report={report}
              busy={busy || analysisLoading}
              onOpenRun={(id) => go(`/scenarios/${scenarioId}?run=${encodeURIComponent(id)}`)}
              emptyHint="Not analyzed yet — use Analyze this test in the header, or Analyze this run on the scenario page."
            />
          </>
        )}
      </section>

      {logOpen ? (
        <section ref={logViewRef} className="panel wide" aria-labelledby="log-view">
          <h2 id="log-view">{logTitle}</h2>
          <StepLogViewer
            title={logTitle}
            document={logDocument}
            error={logError}
            downloadUrl={logDownloadUrl}
            onClose={() => setLogOpen(false)}
          />
        </section>
      ) : null}
    </div>
  )
}
