import { analysisExportUrl, resolveReportOutcome, type AnalysisReport } from '../api'
import { formatDateTime } from '../lib/format'

export function AnalysisPanel({
  report,
  busy,
  onOpenRun,
  emptyHint,
  /** When false, skip status/download chrome (parent section owns header). */
  showChrome = true,
}: {
  report: AnalysisReport | null
  busy: boolean
  onOpenRun: (runId: string) => void
  emptyHint?: string
  showChrome?: boolean
}) {
  if (!report) {
    return (
      <p className="muted">
        {emptyHint ??
          'Run Analyze this run / Analyze this test / Analyze & report to see a structured report.'}
      </p>
    )
  }

  const reliability = resolveReportOutcome(report)
  const isRunScope = report.scope === 'run' || report.scope === 'test'
  const displayReliability =
    reliability === 'no_history' ? 'no history yet' : reliability
  const badgeClass =
    reliability === 'no_history' ? 'status-reliability-unknown' : `status-reliability-${reliability}`
  const statusHint = isRunScope
    ? reliability === 'passed'
      ? 'This run looks clean (no step failures or log health warnings).'
      : reliability === 'failed'
        ? 'Failures found in this run.'
        : reliability === 'watch'
          ? 'Passed steps, but log health warnings (missing/empty/size drift).'
          : 'Outcome not determined.'
    : reliability === 'stable'
      ? 'Within the history window, no high fail-rate slices.'
      : reliability === 'watch'
        ? 'Some tests/setups need attention (fail rate up to 30%).'
        : reliability === 'flaky'
          ? 'At least one (test, SUT, FW) slice is flaky.'
          : 'Not enough history to judge stability yet.'

  return (
    <div className="analysis-report">
      {showChrome ? (
        <div className="log-viewer-header">
          <div>
            <p className="run-meta">
              <span className="status status-finished">{report.scope}</span>
              <span className={`status ${badgeClass}`}>{displayReliability}</span>
              <span className="muted">{formatDateTime(report.generated_at)}</span>
            </p>
            <p className="tight">
              <strong>{report.scenario_name || 'Scenario'}</strong>
              <span className="muted">
                {' '}
                · infra {report.infra} · SUT {report.sut_version} · FW {report.framework_version}
              </span>
            </p>
            <p className="muted tight">{statusHint}</p>
            <p>{report.summary}</p>
          </div>
          <a className="primary" href={analysisExportUrl(report.id)} download>
            Download report + artifacts
          </a>
        </div>
      ) : (
        <div>
          <p className="tight">
            <strong>{report.scenario_name || 'Scenario'}</strong>
            <span className="muted">
              {' '}
              · {formatDateTime(report.generated_at)} · infra {report.infra} · SUT {report.sut_version}{' '}
              · FW {report.framework_version}
            </span>
          </p>
          <p>{report.summary}</p>
        </div>
      )}

      {report.test_analyses && report.test_analyses.length > 0 ? (
        <>
          <h3>Per-test analyses</h3>
          <ul className="tight-list">
            {report.test_analyses.map((ref) => (
              <li key={ref.analysis_id}>
                <code>{ref.test_id}</code> — {ref.error_count} error(s), {ref.health_signal_count}{' '}
                health · {ref.summary}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {report.health_signals && report.health_signals.length > 0 ? (
        <>
          <h3>Log health signals</h3>
          <ul className="tight-list">
            {report.health_signals.map((signal) => (
              <li key={`${signal.test_id}-${signal.kind}-${signal.message}`}>
                <strong>{signal.kind}</strong> · <code>{signal.test_id}</code> — {signal.message}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h3>Errors (fingerprints in scope)</h3>
      {report.errors.length === 0 ? (
        <p className="muted tight">No distinct errors in scope.</p>
      ) : (
        <ul className="analysis-error-list">
          {report.errors.map((err) => (
            <li key={`${err.fingerprint}-${err.label}`}>
              <strong>{err.root_cause_name || err.label || err.fingerprint}</strong>
              <p className="muted tight">
                fingerprint <code>{err.fingerprint}</code> · {err.error_type} · confidence{' '}
                {err.confidence_pct}% · seen {err.occurrence_count}× · components [
                {err.components.join(', ') || '—'}]
              </p>
              <div className="gwt-block">
                <p className="tight">
                  <strong>Given</strong> — {err.given || '—'}
                </p>
                <p className="tight">
                  <strong>When</strong> — {err.when_steps?.length ? err.when_steps.join(' → ') : '—'}
                </p>
                <p className="tight">
                  <strong>Then</strong> — {err.then_actual || '—'}
                </p>
                <p className="tight">
                  <strong>Expected</strong> — {err.expected || '—'}
                </p>
              </div>
              <p className="muted tight">
                Where:{' '}
                {err.where.map((w) => `${w.test_id}.${w.step_id}`).join(', ') || '—'} · SUT [
                {err.sut_versions.join(', ') || '—'}] · FW [{err.framework_versions.join(', ') || '—'}]
              </p>
              {err.recommended_actions.length > 0 ? (
                <ul className="tight-list">
                  {err.recommended_actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              ) : null}
              {err.last_failure_run_id ? (
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => onOpenRun(err.last_failure_run_id!)}
                >
                  Open last failure
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
