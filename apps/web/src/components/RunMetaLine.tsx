import { formatDateTime, formatMs, parseApiDate } from '../lib/format'

/** Shared run identity line used in scenario/test section headers. */
export function RunMetaLine({
  runId,
  status,
  createdAt,
  durationMs,
  extra,
}: {
  runId: string
  status?: string | null
  createdAt?: string | null
  durationMs?: number | null
  extra?: string | null
}) {
  const when = createdAt ? formatDateTime(createdAt) : null
  return (
    <p className="run-meta">
      <span>
        Run <code>{runId}</code>
      </span>
      {status ? <span className={`status status-${status}`}>{status}</span> : null}
      <span className="muted">
        {when ?? '—'}
        {durationMs != null && durationMs !== undefined ? ` · ${formatMs(durationMs)}` : ''}
        {extra ? ` · ${extra}` : ''}
      </span>
    </p>
  )
}

/** Prefer stored duration; while running, fall back to elapsed since created_at. */
export function resolveRunDurationMs(
  run: {
    status: string
    created_at?: string
    duration_ms: number | null
    projection: { scenario_duration_ms: number | null }
  } | null,
  nowMs: number,
): number | null {
  if (!run) return null
  const stored = run.projection.scenario_duration_ms ?? run.duration_ms
  if (stored != null) return stored
  if (!run.created_at) return null
  if (run.status === 'finished' || run.status === 'failed') return null
  const started = parseApiDate(run.created_at).getTime()
  if (Number.isNaN(started)) return null
  return Math.max(0, nowMs - started)
}
