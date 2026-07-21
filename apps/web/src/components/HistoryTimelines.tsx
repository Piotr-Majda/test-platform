import type { FingerprintItem, HistoryRunItem } from '../api'
import { formatDateTime, parseApiDate } from '../lib/format'

function slotPercent(index: number, count: number): number {
  if (count <= 1) return 50
  const pad = 4
  return pad + (index / (count - 1)) * (100 - pad * 2)
}

type TimelineDot = {
  runId: string
  failed: boolean
  title: string
}

function versionMarksFor(axisRuns: HistoryRunItem[]): { key: string; left: number; sut: string; fw: string }[] {
  const marks: { key: string; left: number; sut: string; fw: string }[] = []
  axisRuns.forEach((run, index) => {
    const prev = index > 0 ? axisRuns[index - 1] : null
    const changed =
      !prev ||
      prev.sut_version !== run.sut_version ||
      prev.framework_version !== run.framework_version
    if (changed) {
      marks.push({
        key: `${run.id}-ver`,
        left: slotPercent(index, axisRuns.length),
        sut: run.sut_version,
        fw: run.framework_version,
      })
    }
  })
  return marks
}

function SharedTimeline({
  title,
  subtitle,
  axisRuns,
  dots,
  busy,
  onOpenRun,
}: {
  title: string
  subtitle: string
  axisRuns: HistoryRunItem[]
  dots: TimelineDot[]
  busy: boolean
  onOpenRun: (runId: string) => void
}) {
  const marks = versionMarksFor(axisRuns)
  const indexByRunId = new Map(axisRuns.map((r, i) => [r.id, i]))

  return (
    <div className="timeline-block">
      <h3>{title}</h3>
      <p className="muted tight">{subtitle}</p>
      <div className="version-lane" aria-hidden={marks.length === 0}>
        {marks.map((mark) => (
          <div
            key={mark.key}
            className="version-chip"
            style={{ left: `${mark.left}%` }}
            title={`SUT ${mark.sut} · FW ${mark.fw}`}
          >
            <span>SUT {mark.sut}</span>
            <span>FW {mark.fw}</span>
          </div>
        ))}
      </div>
      <div className="timeline-track" aria-label={title}>
        <div className="timeline-line" />
        {dots.map((dot) => {
          const index = indexByRunId.get(dot.runId)
          if (index == null) return null
          return (
            <button
              key={`${title}-${dot.runId}-${dot.failed ? 'f' : 'p'}`}
              type="button"
              className={`timeline-dot ${dot.failed ? 'fail' : 'ok'}`}
              style={{ left: `${slotPercent(index, axisRuns.length)}%` }}
              disabled={busy}
              title={dot.title}
              onClick={() => onOpenRun(dot.runId)}
            />
          )
        })}
      </div>
    </div>
  )
}

export function HistoryTimelines({
  runs,
  fingerprints,
  busy,
  onOpenRun,
  onAnalyzeFingerprint,
}: {
  runs: HistoryRunItem[]
  fingerprints: FingerprintItem[]
  busy: boolean
  onOpenRun: (runId: string) => void
  onAnalyzeFingerprint: (fingerprint: string) => void
}) {
  const chronological = [...runs].sort(
    (a, b) => parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime(),
  )

  if (chronological.length === 0) {
    return <p className="muted tight">No timeline data yet — run the scenario a few times.</p>
  }

  const failedRuns = chronological.filter((r) => r.status === 'failed')
  const firstIssueT =
    failedRuns.length > 0
      ? parseApiDate(failedRuns[0].created_at).getTime()
      : parseApiDate(chronological[0].created_at).getTime()
  const lastResultT = parseApiDate(chronological[chronological.length - 1].created_at).getTime()
  const axisRuns = chronological.filter((r) => {
    const t = parseApiDate(r.created_at).getTime()
    return t >= firstIssueT && t <= lastResultT
  })

  const runDots: TimelineDot[] = axisRuns.map((item) => ({
    runId: item.id,
    failed: item.status === 'failed',
    title: `${item.status} · SUT ${item.sut_version} · FW ${item.framework_version} · ${formatDateTime(item.created_at)}`,
  }))

  const fps = fingerprints.filter((fp) => (fp.timeline ?? []).length > 0)

  return (
    <div className="timelines">
      <SharedTimeline
        title="Run timeline"
        subtitle="Green = pass, red = fail. SUT / FW chips mark version changes. Click a dot to open the run."
        axisRuns={axisRuns}
        dots={runDots}
        busy={busy}
        onOpenRun={onOpenRun}
      />

      <h3 className="timeline-section-title">Error fingerprint timelines</h3>
      <p className="muted tight">
        Same layout as the run timeline. Red = this error on that run; green = run without this fingerprint.
      </p>
      {fps.length === 0 ? (
        <p className="muted tight">No fingerprint events in the current history window.</p>
      ) : (
        fps.map((fp) => {
          const hitRuns = new Set(fp.timeline.map((o) => o.run_id))
          const dots: TimelineDot[] = axisRuns.map((item) => {
            const hit = hitRuns.has(item.id)
            return {
              runId: item.id,
              failed: hit,
              title: hit
                ? `${fp.label} · SUT ${item.sut_version} · FW ${item.framework_version} · ${formatDateTime(item.created_at)}`
                : `no ${fp.fingerprint} · ${item.status} · SUT ${item.sut_version} · FW ${item.framework_version}`,
            }
          })
          return (
            <div key={`${fp.fingerprint}-${fp.test_id}-${fp.step_id}`} className="fingerprint-analyze-block">
              <div className="row-actions timeline-analyze-actions">
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => onAnalyzeFingerprint(fp.fingerprint)}
                >
                  Analyze error
                </button>
              </div>
              <SharedTimeline
                title={`${fp.fingerprint} · ${fp.test_id} / ${fp.step_id}`}
                subtitle={fp.label}
                axisRuns={axisRuns}
                dots={dots}
                busy={busy}
                onOpenRun={onOpenRun}
              />
            </div>
          )
        })
      )}
    </div>
  )
}

export function TestStabilityTimelines({
  runs,
  rollups,
  flakiness,
  busy,
  onOpenRun,
}: {
  runs: HistoryRunItem[]
  rollups: {
    test_id: string
    fail_rate: number
    reliability: string
    failed_runs: number
    total_runs: number
  }[]
  flakiness?: {
    test_id: string
    sut_version: string
    framework_version: string
    fail_rate: number
    reliability: string
    failed_runs: number
    total_runs: number
  }[]
  busy: boolean
  onOpenRun: (runId: string) => void
}) {
  const chronological = [...runs].sort(
    (a, b) => parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime(),
  )
  if (chronological.length === 0 || rollups.length === 0) {
    return <p className="muted tight">No per-test timeline data yet.</p>
  }

  return (
    <div className="timelines">
      {rollups.map((item) => {
        const axisRuns = chronological.filter((run) => run.test_results?.[item.test_id])
        if (axisRuns.length === 0) return null
        const dots: TimelineDot[] = axisRuns.map((run) => {
          const status = run.test_results?.[item.test_id] ?? 'finished'
          const failed = status === 'failed'
          return {
            runId: run.id,
            failed,
            title: `${item.test_id} · ${failed ? 'failed' : 'passed'} · SUT ${run.sut_version} · FW ${run.framework_version} · ${formatDateTime(run.created_at)}`,
          }
        })
        const setups = (flakiness ?? []).filter((f) => f.test_id === item.test_id)
        const setupSummary =
          setups.length === 0
            ? ''
            : ' · ' +
              setups
                .map(
                  (s) =>
                    `SUT ${s.sut_version}/FW ${s.framework_version}: ${s.reliability} (${(s.fail_rate * 100).toFixed(0)}%, ${s.failed_runs}/${s.total_runs})`,
                )
                .join('; ')
        return (
          <SharedTimeline
            key={item.test_id}
            title={item.test_id}
            subtitle={`${item.reliability} · fail rate ${(item.fail_rate * 100).toFixed(0)}% · ${item.failed_runs}/${item.total_runs} runs${setupSummary}`}
            axisRuns={axisRuns}
            dots={dots}
            busy={busy}
            onOpenRun={onOpenRun}
          />
        )
      })}
    </div>
  )
}
