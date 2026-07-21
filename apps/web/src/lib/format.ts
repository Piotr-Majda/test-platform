import type { StepView } from '../api'

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

export function formatDurationTrend(direction: string, deltaMs: number | null | undefined): string {
  if (direction === 'faster') return `faster${deltaMs != null ? ` (${deltaMs} ms)` : ''}`
  if (direction === 'slower') return `slower${deltaMs != null ? ` (+${deltaMs} ms)` : ''}`
  if (direction === 'steady' || direction === 'stable') return 'steady'
  return '—'
}

/**
 * API timestamps are UTC. Naive ISO strings (no Z / offset) must be parsed as UTC,
 * otherwise the browser treats them as local and Poland (UTC+2) shows 2 hours early.
 */
export function parseApiDate(value: string): Date {
  const trimmed = value.trim()
  if (!trimmed) return new Date(NaN)
  if (/([zZ]|[+-]\d{2}:?\d{2})$/.test(trimmed)) {
    return new Date(trimmed)
  }
  const iso = trimmed.includes('T') ? trimmed : trimmed.replace(' ', 'T')
  return new Date(`${iso}Z`)
}

/** Format API datetime in the user's system timezone. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString()
}

/** Group steps under tests; prefer catalog/test order from the projection. */
export function groupStepsByTest(
  steps: StepView[],
  tests: { test_id: string }[],
): { testId: string | null; steps: StepView[] }[] {
  const byTest = new Map<string, StepView[]>()
  for (const step of steps) {
    const key = step.test_id ?? ''
    if (!byTest.has(key)) byTest.set(key, [])
    byTest.get(key)!.push(step)
  }

  const groups: { testId: string | null; steps: StepView[] }[] = []
  const seen = new Set<string>()
  for (const test of tests) {
    seen.add(test.test_id)
    groups.push({ testId: test.test_id, steps: byTest.get(test.test_id) ?? [] })
  }
  for (const [key, groupSteps] of byTest) {
    if (key === '' || seen.has(key)) continue
    groups.push({ testId: key, steps: groupSteps })
  }
  const orphaned = byTest.get('') ?? []
  if (orphaned.length > 0) {
    groups.push({ testId: null, steps: orphaned })
  }
  return groups.filter((g) => g.steps.length > 0)
}
