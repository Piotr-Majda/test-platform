// Prefer same-origin Vite proxy (/api → :8001) so browser fetch (logs, etc.) is not cross-origin.
const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

export type TestDefinition = {
  id: string
  name: string
  description: string
  steps: string[]
}

export type HistoryConfig = {
  max_runs: number | null
  max_days: number | null
}

export type ArtifactRetentionConfig = {
  max_runs: number | null
  max_days: number | null
  keep_at_least_one_failed: boolean
}

export type Scenario = {
  id: string
  name: string
  test_ids: string[]
  sut_version: string
  history: HistoryConfig
  artifacts: ArtifactRetentionConfig
}

export const DEFAULT_ARTIFACT_RETENTION: ArtifactRetentionConfig = {
  max_runs: 20,
  max_days: null,
  keep_at_least_one_failed: true,
}

export const DEFAULT_HISTORY: HistoryConfig = {
  max_runs: 50,
  max_days: null,
}

/** Guard against older API payloads missing retention fields (avoids blank UI). */
export function normalizeScenario(raw: Scenario): Scenario {
  return {
    ...raw,
    history: {
      max_runs: raw.history?.max_runs ?? DEFAULT_HISTORY.max_runs,
      max_days: raw.history?.max_days ?? null,
    },
    artifacts: {
      max_runs: raw.artifacts?.max_runs ?? DEFAULT_ARTIFACT_RETENTION.max_runs,
      max_days: raw.artifacts?.max_days ?? null,
      keep_at_least_one_failed:
        raw.artifacts?.keep_at_least_one_failed ?? DEFAULT_ARTIFACT_RETENTION.keep_at_least_one_failed,
    },
  }
}

export type ArtifactRef = {
  id: string
  kind: string
  name: string
  content_type: string
  relative_path: string
}

export type StepView = {
  name: string
  status: string
  duration_ms: number | null
  test_id: string | null
  error_message: string | null
  error_trace: string | null
  artifacts: ArtifactRef[]
}

export type TestView = {
  test_id: string
  status: string
  duration_ms: number | null
}

export type RunDetail = {
  id: string
  scenario_id: string
  status: string
  sut_version: string
  framework_version: string
  duration_ms: number | null
  created_at?: string
  projection: {
    steps: StepView[]
    tests: TestView[]
    scenario_duration_ms: number | null
  }
}

export type HistoryRunItem = {
  id: string
  status: string
  sut_version: string
  framework_version: string
  duration_ms: number | null
  created_at: string
  test_results?: Record<string, string>
}

export type DurationTrend = {
  last_duration_ms: number | null
  previous_avg_ms: number | null
  delta_ms: number | null
  direction: string
}

export type StepHistoryItem = {
  step_id: string
  total: number
  failed: number
  fail_rate: number
  avg_duration_ms: number | null
  trend: DurationTrend
  reliability: string
}

export type FlakinessItem = {
  test_id: string
  sut_version: string
  framework_version: string
  total_runs: number
  failed_runs: number
  fail_rate: number
  avg_duration_ms: number | null
  min_duration_ms: number | null
  max_duration_ms: number | null
  trend: DurationTrend
  reliability: string
  steps: StepHistoryItem[]
}

export type FailureOccurrence = {
  run_id: string
  test_id: string
  step_id: string
  message: string
  created_at: string
}

export type FingerprintItem = {
  fingerprint: string
  label: string
  step_id: string
  test_id: string
  sut_version: string
  framework_version: string
  count: number
  recent_failures: FailureOccurrence[]
  /** Occurrences inside scenario history retention (max_runs ∩ max_days). */
  timeline: FailureOccurrence[]
}

export type ScenarioHistory = {
  scenario_id: string
  runs: HistoryRunItem[]
  flakiness: FlakinessItem[]
  fingerprints: FingerprintItem[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const text = await response.text()
    if (response.status === 401 && path !== '/auth/login') {
      window.dispatchEvent(new Event('tp:unauthorized'))
    }
    try {
      const payload = JSON.parse(text) as { detail?: string }
      throw new Error(payload.detail || `HTTP ${response.status}`)
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text || `HTTP ${response.status}`)
      throw error
    }
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export type AuthRole = 'admin' | 'viewer' | 'guest'

export type AuthUser = {
  username: string
  role: AuthRole
}

export function login(username: string, password: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function loginAsGuest(): Promise<AuthUser> {
  return request<AuthUser>('/auth/guest', {
    method: 'POST',
  })
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

export function getCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>('/auth/me')
}

export function listTests(): Promise<TestDefinition[]> {
  return request<TestDefinition[]>('/tests')
}

export async function listScenarios(): Promise<Scenario[]> {
  const items = await request<Scenario[]>('/scenarios')
  return items.map(normalizeScenario)
}

export async function createScenario(input: {
  name: string
  testIds: string[]
  sutVersion: string
  history: HistoryConfig
  artifacts: ArtifactRetentionConfig
}): Promise<Scenario> {
  const created = await request<Scenario>('/scenarios', {
    method: 'POST',
    body: JSON.stringify({
      name: input.name,
      test_ids: input.testIds,
      sut_version: input.sutVersion,
      history: input.history,
      artifacts: input.artifacts,
    }),
  })
  return normalizeScenario(created)
}

export async function updateScenario(
  scenarioId: string,
  body: {
    sut_version?: string
    history?: HistoryConfig
    artifacts?: ArtifactRetentionConfig
    name?: string
    test_ids?: string[]
  },
): Promise<Scenario> {
  const updated = await request<Scenario>(`/scenarios/${scenarioId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return normalizeScenario(updated)
}

export function deleteScenario(scenarioId: string): Promise<void> {
  return request<void>(`/scenarios/${scenarioId}`, { method: 'DELETE' })
}

export function startRun(scenarioId: string): Promise<{ id: string; status: string }> {
  return request(`/scenarios/${scenarioId}/runs`, { method: 'POST' })
}

export function getRun(runId: string): Promise<RunDetail> {
  return request<RunDetail>(`/runs/${runId}`)
}

export function getScenarioHistory(scenarioId: string): Promise<ScenarioHistory> {
  return request<ScenarioHistory>(`/scenarios/${scenarioId}/history`)
}

export type AnalysisScope = 'run' | 'test' | 'fingerprint' | 'scenario'

export type FailureWhere = {
  test_id: string
  step_id: string
}

export type HealthSignal = {
  test_id: string
  kind: string
  severity: string
  message: string
  current_bytes: number | null
  baseline_median_bytes: number | null
}

export type TestAnalysisRef = {
  test_id: string
  analysis_id: string
  summary: string
  health_signal_count: number
  error_count: number
}

export type ErrorAnalysisItem = {
  fingerprint: string
  label: string
  description: string
  where: FailureWhere[]
  occurrence_count: number
  last_failure_run_id: string | null
  sut_versions: string[]
  framework_versions: string[]
  given: string
  when_steps: string[]
  then_actual: string
  expected: string
  root_cause_name: string
  confidence_pct: number
  error_type: string
  components: string[]
  reproduce_path: string
  likely_sut_issue: boolean
  recommended_actions: string[]
}

export type FlakinessSnapshot = {
  test_id: string
  sut_version: string
  framework_version: string
  total_runs: number
  failed_runs: number
  fail_rate: number
  reliability: string
}

export type AnalysisReport = {
  id: string
  scope: AnalysisScope
  scenario_id: string | null
  scenario_name: string
  run_id: string | null
  test_id: string | null
  fingerprint: string | null
  parent_analysis_id: string | null
  sut_version: string
  framework_version: string
  infra: string
  summary: string
  scenario_reliability?: string
  errors: ErrorAnalysisItem[]
  flakiness: FlakinessSnapshot[]
  health_signals: HealthSignal[]
  test_analyses: TestAnalysisRef[]
  generated_at: string
}

export type AnalysisJobStatus = {
  id: string
  status: 'pending' | 'completed' | 'failed' | string
  report: AnalysisReport | null
  error: string | null
}

export type RunAnalysisBundle = {
  run: AnalysisReport | null
  tests: Record<string, AnalysisReport>
}

export function startAnalysis(body: {
  scope: AnalysisScope
  scenario_id?: string
  run_id?: string
  test_id?: string
  fingerprint?: string
}): Promise<AnalysisJobStatus> {
  return request<AnalysisJobStatus>('/analyses', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getAnalysisJob(jobId: string): Promise<AnalysisJobStatus> {
  return request<AnalysisJobStatus>(`/analyses/jobs/${jobId}`)
}

export async function getRunAnalysis(runId: string): Promise<RunAnalysisBundle> {
  return request<RunAnalysisBundle>(`/runs/${encodeURIComponent(runId)}/analysis`)
}

/** Soft load — 404 / missing route means "no saved analysis", not a UI error. */
export async function tryGetRunAnalysis(runId: string): Promise<RunAnalysisBundle | null> {
  try {
    return await getRunAnalysis(runId)
  } catch {
    return null
  }
}

export function getTestAnalysis(runId: string, testId: string): Promise<AnalysisReport> {
  return request<AnalysisReport>(
    `/runs/${encodeURIComponent(runId)}/tests/${encodeURIComponent(testId)}/analysis`,
  )
}

export async function tryGetTestAnalysis(
  runId: string,
  testId: string,
): Promise<AnalysisReport | null> {
  try {
    return await getTestAnalysis(runId, testId)
  } catch {
    return null
  }
}

export function getAnalysis(analysisId: string): Promise<AnalysisReport> {
  return request<AnalysisReport>(`/analyses/${encodeURIComponent(analysisId)}`)
}

const RUN_ANALYSIS_CACHE_KEY = (runId: string) => `tp.v2.runAnalysis.${runId}`

export function cacheRunAnalysis(runId: string, bundle: RunAnalysisBundle): void {
  try {
    sessionStorage.setItem(RUN_ANALYSIS_CACHE_KEY(runId), JSON.stringify(bundle))
  } catch {
    /* ignore quota */
  }
}

export function readCachedRunAnalysis(runId: string): RunAnalysisBundle | null {
  try {
    const raw = sessionStorage.getItem(RUN_ANALYSIS_CACHE_KEY(runId))
    if (!raw) return null
    return JSON.parse(raw) as RunAnalysisBundle
  } catch {
    return null
  }
}

/** Resolve outcome for display — never leave a scary "unknown" when we can infer. */
export function resolveReportOutcome(report: AnalysisReport): string {
  const raw = (report.scenario_reliability || '').toLowerCase()
  if (raw && raw !== 'unknown') return raw

  if (report.scope === 'run' || report.scope === 'test') {
    if ((report.errors?.length ?? 0) > 0) return 'failed'
    if ((report.health_signals ?? []).some((s) => s.severity === 'warn')) return 'watch'
    return 'passed'
  }

  const flakes = report.flakiness ?? []
  if (flakes.length === 0) return 'no_history'
  const worst = Math.max(...flakes.map((f) => f.fail_rate))
  if (worst <= 0.1) return 'stable'
  if (worst <= 0.3) return 'watch'
  return 'flaky'
}

export function analysisExportUrl(analysisId: string): string {
  return `${API_BASE}/analyses/${encodeURIComponent(analysisId)}/export`
}

/** Start analysis and poll until completed/failed (UI stays free to do other work). */
export async function runAnalysisAndWait(
  body: {
    scope: AnalysisScope
    scenario_id?: string
    run_id?: string
    test_id?: string
    fingerprint?: string
  },
  options?: { intervalMs?: number; timeoutMs?: number },
): Promise<AnalysisReport> {
  const intervalMs = options?.intervalMs ?? 500
  const timeoutMs = options?.timeoutMs ?? 180_000
  const started = await startAnalysis(body)
  const deadline = Date.now() + timeoutMs
  let job = started
  while (job.status === 'pending') {
    if (Date.now() > deadline) {
      throw new Error('Analysis timed out — try again or check API logs')
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    job = await getAnalysisJob(started.id)
  }
  if (job.status === 'failed' || !job.report) {
    throw new Error(job.error || 'Analysis failed')
  }
  return job.report
}

export function artifactUrl(relativePath: string): string {
  const encoded = relativePath
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/')
  return `${API_BASE}/artifacts/${encoded}`
}

export type LogNode = {
  timestamp: string
  layer: string
  message: string
  component?: string
  level: string
  duration_ms?: number | null
  event?: string
  data?: Record<string, unknown>
  children?: LogNode[]
}

export type StepLogDocument = {
  schema_version: string
  scope: 'step'
  test_id: string | null
  step_id: string
  status: string
  duration_ms?: number | null
  entries: LogNode[]
}

export type TestLogDocument = {
  schema_version: string
  scope: 'test'
  test_id: string
  steps: StepLogDocument[]
}

export type LogDocument = StepLogDocument | TestLogDocument

export function isTestLogDocument(doc: LogDocument): doc is TestLogDocument {
  return Array.isArray((doc as TestLogDocument).steps)
}

export function fetchTestLogs(runId: string, testId: string): Promise<TestLogDocument> {
  return request<TestLogDocument>(
    `/runs/${encodeURIComponent(runId)}/tests/${encodeURIComponent(testId)}/logs`,
  )
}

export function fetchStepLogs(
  runId: string,
  testId: string,
  stepId: string,
): Promise<StepLogDocument> {
  return request<StepLogDocument>(
    `/runs/${encodeURIComponent(runId)}/tests/${encodeURIComponent(testId)}/steps/${encodeURIComponent(stepId)}/logs`,
  )
}
