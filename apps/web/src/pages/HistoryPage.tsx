import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  analysisExportUrl,
  getScenarioHistory,
  listScenarios,
  runAnalysisAndWait,
  type AnalysisReport,
  type FlakinessItem,
  type Scenario,
  type ScenarioHistory,
} from '../api'
import { AnalysisPanel } from '../components/AnalysisPanel'
import { HistoryTimelines, TestStabilityTimelines } from '../components/HistoryTimelines'
import { formatDateTime, formatMs } from '../lib/format'
import { PageSubHeader } from '../layout/PageSubHeader'
import { useNavStack } from '../navigation/NavStack'

type TestStabilityRollup = {
  test_id: string
  total_runs: number
  failed_runs: number
  fail_rate: number
  reliability: string
  setups: number
}

function reliabilityFromRate(failRate: number): string {
  if (failRate <= 0.1) return 'stable'
  if (failRate <= 0.3) return 'watch'
  return 'flaky'
}

function rollupFlakinessByTest(items: FlakinessItem[]): TestStabilityRollup[] {
  const byTest = new Map<string, { total: number; failed: number; setups: number }>()
  for (const item of items) {
    const cur = byTest.get(item.test_id) ?? { total: 0, failed: 0, setups: 0 }
    cur.total += item.total_runs
    cur.failed += item.failed_runs
    cur.setups += 1
    byTest.set(item.test_id, cur)
  }
  return [...byTest.entries()]
    .map(([test_id, cur]) => {
      const fail_rate = cur.total === 0 ? 0 : cur.failed / cur.total
      return {
        test_id,
        total_runs: cur.total,
        failed_runs: cur.failed,
        fail_rate,
        reliability: reliabilityFromRate(fail_rate),
        setups: cur.setups,
      }
    })
    .sort((a, b) => b.fail_rate - a.fail_rate || a.test_id.localeCompare(b.test_id))
}

export function HistoryPage() {
  const { scenarioId = '' } = useParams()
  const { go } = useNavStack()
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [history, setHistory] = useState<ScenarioHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy] = useState(false)
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const analysisViewRef = useRef<HTMLElement | null>(null)

  const load = useCallback(async () => {
    if (!scenarioId) return
    setError(null)
    try {
      const [all, hist] = await Promise.all([listScenarios(), getScenarioHistory(scenarioId)])
      setScenario(all.find((s) => s.id === scenarioId) ?? null)
      setHistory(hist)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history')
    }
  }, [scenarioId])

  useEffect(() => {
    void load()
  }, [load])

  const testRollup = useMemo(
    () => (history ? rollupFlakinessByTest(history.flakiness) : []),
    [history],
  )

  const scenarioReliability = useMemo(() => {
    if (analysis?.scenario_reliability && analysis.scope === 'scenario') {
      return analysis.scenario_reliability
    }
    if (testRollup.length === 0) return 'unknown'
    const worst = Math.max(...testRollup.map((t) => t.fail_rate))
    return reliabilityFromRate(worst)
  }, [analysis, testRollup])

  const focusAnalysis = () => {
    window.requestAnimationFrame(() => {
      analysisViewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  const openRun = (runId: string) => {
    go(`/scenarios/${scenarioId}?run=${encodeURIComponent(runId)}&from=history`)
  }

  const analyzeScenario = () => {
    if (!scenarioId) return
    setAnalysisLoading(true)
    setAnalysisError(null)
    setAnalysis(null)
    focusAnalysis()
    void runAnalysisAndWait({ scope: 'scenario', scenario_id: scenarioId })
      .then(setAnalysis)
      .catch((err) => setAnalysisError(err instanceof Error ? err.message : 'Analysis failed'))
      .finally(() => setAnalysisLoading(false))
  }

  const analyzeFingerprint = (fingerprint: string) => {
    if (!scenarioId) return
    setAnalysisLoading(true)
    setAnalysisError(null)
    setAnalysis(null)
    focusAnalysis()
    void runAnalysisAndWait({ scope: 'fingerprint', scenario_id: scenarioId, fingerprint })
      .then(setAnalysis)
      .catch((err) => setAnalysisError(err instanceof Error ? err.message : 'Analysis failed'))
      .finally(() => setAnalysisLoading(false))
  }

  const analyzeRun = (runId: string) => {
    setAnalysisLoading(true)
    setAnalysisError(null)
    setAnalysis(null)
    focusAnalysis()
    void runAnalysisAndWait({ scope: 'run', run_id: runId })
      .then(setAnalysis)
      .catch((err) => setAnalysisError(err instanceof Error ? err.message : 'Analysis failed'))
      .finally(() => setAnalysisLoading(false))
  }

  if (!history && !error) {
    return (
      <div className="page">
        <p className="muted">Loading history…</p>
      </div>
    )
  }

  return (
    <div className="page">
      <PageSubHeader>
        <div className="page-subhead-inner">
          <div>
            <h1>History · {scenario?.name ?? scenarioId}</h1>
            <p className="lede tight">Flakiness, runs, timelines — analyze & download report here.</p>
          </div>
          <div className="row-actions">
            <button type="button" className="primary" onClick={() => go(`/scenarios/${scenarioId}`)}>
              Back to scenario
            </button>
            <button type="button" className="ghost" disabled={analysisLoading} onClick={analyzeScenario}>
              {analysisLoading ? 'Analyzing…' : 'Analyze & report'}
            </button>
          </div>
        </div>
      </PageSubHeader>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {history ? (
        <section className="panel wide">
          <div className="totals">
            <h3>Runs</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Status</th>
                  <th>SUT</th>
                  <th>FW</th>
                  <th>Time</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {history.runs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="muted">
                      No runs in the history window yet.
                    </td>
                  </tr>
                ) : (
                  history.runs.map((item) => (
                    <tr key={item.id}>
                      <td>{formatDateTime(item.created_at)}</td>
                      <td>
                        <span className={`status status-${item.status === 'failed' ? 'failed' : 'finished'}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>{item.sut_version}</td>
                      <td>{item.framework_version}</td>
                      <td>{formatMs(item.duration_ms)}</td>
                      <td>
                        <div className="row-actions">
                          <button type="button" className="ghost" disabled={busy} onClick={() => openRun(item.id)}>
                            Open run
                          </button>
                          <button
                            type="button"
                            className="ghost"
                            disabled={analysisLoading || item.status !== 'failed'}
                            onClick={() => analyzeRun(item.id)}
                          >
                            Analyze run
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="totals">
            <h3>Timelines</h3>
            <HistoryTimelines
              runs={history.runs}
              fingerprints={history.fingerprints ?? []}
              busy={busy || analysisLoading}
              onOpenRun={(runId) => openRun(runId)}
              onAnalyzeFingerprint={analyzeFingerprint}
            />
          </div>
        </section>
      ) : null}

      <section ref={analysisViewRef} className="panel wide" aria-labelledby="history-analysis">
        <div className="log-viewer-header">
          <div>
            <h2 id="history-analysis">Analyze & report</h2>
            <p className="run-meta">
              <span
                className={`status status-reliability-${scenarioReliability === 'unknown' ? 'unknown' : scenarioReliability}`}
              >
                {scenarioReliability === 'unknown' ? 'no history yet' : scenarioReliability}
              </span>
              <span className="muted">
                Scenario reliability from history
                {scenarioReliability === 'stable'
                  ? ' — no high fail-rate tests in the window.'
                  : scenarioReliability === 'watch'
                    ? ' — some tests need attention.'
                    : scenarioReliability === 'flaky'
                      ? ' — at least one test is flaky.'
                      : ' — not enough data yet.'}
              </span>
            </p>
          </div>
          {analysis ? (
            <a className="primary" href={analysisExportUrl(analysis.id)} download>
              Download report + artifacts
            </a>
          ) : null}
        </div>

        {analysisLoading ? (
          <p className="muted">Analyzing…</p>
        ) : (
          <>
            {analysisError ? <p className="error">{analysisError}</p> : null}
            <AnalysisPanel
              report={analysis}
              busy={busy}
              showChrome={false}
              onOpenRun={(runId) => openRun(runId)}
              emptyHint="Click Analyze & report in the header to generate a history report."
            />
            <div className="totals">
              <h3>Per-test stability timelines</h3>
              <p className="muted tight">
                Green = passed, red = failed. Summary includes fail rate, reliability, and SUT/FW setups.
              </p>
              {history ? (
                <TestStabilityTimelines
                  runs={history.runs}
                  rollups={testRollup}
                  flakiness={history.flakiness}
                  busy={busy || analysisLoading}
                  onOpenRun={(runId) => openRun(runId)}
                />
              ) : null}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
