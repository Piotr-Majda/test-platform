import { useState } from 'react'
import {
  DEFAULT_ARTIFACT_RETENTION,
  DEFAULT_HISTORY,
  type ArtifactRetentionConfig,
  type HistoryConfig,
  type TestDefinition,
} from './api'

export type ScenarioFormValues = {
  name: string
  sutVersion: string
  history: HistoryConfig
  artifacts: ArtifactRetentionConfig
  testIds: string[]
}

type Props = {
  title: string
  submitLabel: string
  busy?: boolean
  availableTests: TestDefinition[]
  initial: ScenarioFormValues
  onSubmit: (values: ScenarioFormValues) => void | Promise<void>
  onCancel: () => void
}

function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items
  const next = [...items]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

export function ScenarioConfigForm({
  title,
  submitLabel,
  busy = false,
  availableTests,
  initial,
  onSubmit,
  onCancel,
}: Props) {
  const [name, setName] = useState(initial.name)
  const [sutVersion, setSutVersion] = useState(initial.sutVersion)
  const [historyMaxRuns, setHistoryMaxRuns] = useState(initial.history.max_runs?.toString() ?? '')
  const [historyMaxDays, setHistoryMaxDays] = useState(initial.history.max_days?.toString() ?? '')
  const [artifactMaxRuns, setArtifactMaxRuns] = useState(initial.artifacts.max_runs?.toString() ?? '')
  const [artifactMaxDays, setArtifactMaxDays] = useState(initial.artifacts.max_days?.toString() ?? '')
  const [keepAtLeastOneFailed, setKeepAtLeastOneFailed] = useState(
    initial.artifacts.keep_at_least_one_failed,
  )
  const [testIds, setTestIds] = useState(initial.testIds)
  const [dragOver, setDragOver] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const resolvedTests = testIds.map(
    (id) => availableTests.find((t) => t.id === id) ?? { id, name: id, description: '', steps: [] },
  )

  const parseOptionalInt = (value: string): number | null =>
    value.trim() === '' ? null : Number(value)

  const handleSubmit = async () => {
    if (!name.trim()) {
      setLocalError('Scenario name is required')
      return
    }
    if (testIds.length === 0) {
      setLocalError('Add at least one test (drag from Available tests or use Add)')
      return
    }
    setLocalError(null)
    await onSubmit({
      name: name.trim(),
      sutVersion: sutVersion.trim() || 'unknown',
      history: {
        max_runs: parseOptionalInt(historyMaxRuns),
        max_days: parseOptionalInt(historyMaxDays),
      },
      artifacts: {
        max_runs: parseOptionalInt(artifactMaxRuns),
        max_days: parseOptionalInt(artifactMaxDays),
        keep_at_least_one_failed: keepAtLeastOneFailed,
      },
      testIds,
    })
  }

  const addTest = (testId: string) => {
    setTestIds((prev) => [...prev, testId])
  }

  return (
    <section className="panel wide scenario-config" aria-labelledby="scenario-config-title">
      <div className="panel-head">
        <h2 id="scenario-config-title">{title}</h2>
        <button type="button" className="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>

      {localError ? (
        <p className="error tight" role="alert">
          {localError}
        </p>
      ) : null}

      <label className="field">
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        SUT version
        <input value={sutVersion} onChange={(e) => setSutVersion(e.target.value)} />
      </label>

      <h3 className="subsection-title">Run history retention</h3>
      <p className="muted tight">Keeps run records for flakiness and timelines (max runs ∩ max days).</p>
      <div className="field-row">
        <label className="field">
          Max runs
          <input value={historyMaxRuns} onChange={(e) => setHistoryMaxRuns(e.target.value)} placeholder="50" />
        </label>
        <label className="field">
          Max days
          <input value={historyMaxDays} onChange={(e) => setHistoryMaxDays(e.target.value)} placeholder="optional" />
        </label>
      </div>

      <h3 className="subsection-title">Artifact retention</h3>
      <p className="muted tight">
        Keep disk artifacts for the last N runs. With “keep at least one failed”, also retain the
        newest failed run that still sits inside the history window (even if older than N).
      </p>
      <div className="field-row">
        <label className="field">
          Max runs
          <input value={artifactMaxRuns} onChange={(e) => setArtifactMaxRuns(e.target.value)} placeholder="20" />
        </label>
        <label className="field">
          Max days
          <input value={artifactMaxDays} onChange={(e) => setArtifactMaxDays(e.target.value)} placeholder="optional" />
        </label>
        <label className="field checkbox-field">
          <span>Keep ≥1 failed in history</span>
          <input
            type="checkbox"
            checked={keepAtLeastOneFailed}
            onChange={(e) => setKeepAtLeastOneFailed(e.target.checked)}
          />
        </label>
      </div>

      <h3 className="subsection-title">Tests (execution order)</h3>
      <p className="muted tight">Drag tests here, or add from the list. Use ↑ / ↓ to reorder.</p>
      <div className="field-row">
        <label className="field">
          Add test
          <select
            defaultValue=""
            onChange={(e) => {
              const value = e.target.value
              if (value) {
                addTest(value)
                e.target.value = ''
              }
            }}
          >
            <option value="" disabled>
              Select a test…
            </option>
            {availableTests.map((test) => (
              <option key={test.id} value={test.id}>
                {test.name} ({test.id})
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        className={`dropzone ${dragOver ? 'active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragOver(false)
          const testId = event.dataTransfer.getData('text/test-id')
          if (testId) addTest(testId)
        }}
      >
        {resolvedTests.length === 0 ? (
          <p className="muted">Drop tests here to build an ordered scenario</p>
        ) : (
          <ol className="draft-list">
            {resolvedTests.map((test, index) => (
              <li key={`${test.id}-${index}`}>
                <span>
                  {index + 1}. {test.name}
                </span>
                <div className="row-actions">
                  <button
                    type="button"
                    className="ghost"
                    disabled={index === 0}
                    aria-label="Move up"
                    onClick={() => setTestIds((prev) => moveItem(prev, index, index - 1))}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={index === resolvedTests.length - 1}
                    aria-label="Move down"
                    onClick={() => setTestIds((prev) => moveItem(prev, index, index + 1))}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setTestIds((prev) => prev.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="row-actions">
        <button type="button" className="primary" disabled={busy} onClick={() => void handleSubmit()}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  )
}

export function defaultCreateValues(): ScenarioFormValues {
  return {
    name: 'Smoke scenario',
    sutVersion: '1.0.0',
    history: { ...DEFAULT_HISTORY },
    artifacts: { ...DEFAULT_ARTIFACT_RETENTION },
    testIds: [],
  }
}

export function valuesFromScenario(scenario: {
  name: string
  sut_version: string
  history?: HistoryConfig | null
  artifacts?: ArtifactRetentionConfig | null
  test_ids: string[]
}): ScenarioFormValues {
  return {
    name: scenario.name,
    sutVersion: scenario.sut_version,
    history: {
      max_runs: scenario.history?.max_runs ?? DEFAULT_HISTORY.max_runs,
      max_days: scenario.history?.max_days ?? null,
    },
    artifacts: {
      max_runs: scenario.artifacts?.max_runs ?? DEFAULT_ARTIFACT_RETENTION.max_runs,
      max_days: scenario.artifacts?.max_days ?? null,
      keep_at_least_one_failed:
        scenario.artifacts?.keep_at_least_one_failed ??
        DEFAULT_ARTIFACT_RETENTION.keep_at_least_one_failed,
    },
    testIds: [...scenario.test_ids],
  }
}
