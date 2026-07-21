import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createScenario,
  listScenarios,
  listTests,
  updateScenario,
  type Scenario,
  type TestDefinition,
} from '../api'
import {
  ScenarioConfigForm,
  defaultCreateValues,
  valuesFromScenario,
  type ScenarioFormValues,
} from '../ScenarioConfigForm'
import { useNavStack } from '../navigation/NavStack'

export function ScenarioConfigPage({ mode }: { mode: 'new' | 'edit' }) {
  const { scenarioId } = useParams()
  const { go, back, cancelTo } = useNavStack()
  const [tests, setTests] = useState<TestDefinition[]>([])
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(mode === 'new')

  const load = useCallback(async () => {
    setError(null)
    try {
      const catalog = await listTests()
      setTests(catalog)
      if (mode === 'edit' && scenarioId) {
        const all = await listScenarios()
        const found = all.find((s) => s.id === scenarioId) ?? null
        if (!found) {
          setError('Scenario not found')
          setReady(true)
          return
        }
        setScenario(found)
      }
      setReady(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
      setReady(true)
    }
  }, [mode, scenarioId])

  useEffect(() => {
    void load()
  }, [load])

  const onSubmit = async (values: ScenarioFormValues) => {
    setBusy(true)
    setError(null)
    try {
      if (mode === 'edit' && scenarioId) {
        await updateScenario(scenarioId, {
          name: values.name,
          sut_version: values.sutVersion,
          test_ids: values.testIds,
          history: values.history,
          artifacts: values.artifacts,
        })
        go(`/scenarios/${scenarioId}`)
      } else {
        const created = await createScenario({
          name: values.name,
          testIds: values.testIds,
          sutVersion: values.sutVersion,
          history: values.history,
          artifacts: values.artifacts,
        })
        go(`/scenarios/${created.id}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  if (!ready) {
    return (
      <div className="page">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (mode === 'edit' && !scenario) {
    return (
      <div className="page">
        <p className="error">{error ?? 'Scenario not found'}</p>
        <button type="button" className="ghost" onClick={() => cancelTo('/')}>
          Back to scenarios
        </button>
      </div>
    )
  }

  return (
    <div className="page">
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="config-stack">
        <ScenarioConfigForm
          key={mode === 'edit' ? scenario!.id : 'new'}
          title={mode === 'edit' ? `Configure · ${scenario!.name}` : 'Create scenario'}
          submitLabel={mode === 'edit' ? 'Save changes' : 'Save scenario'}
          busy={busy}
          availableTests={tests}
          initial={mode === 'edit' ? valuesFromScenario(scenario!) : defaultCreateValues()}
          onSubmit={onSubmit}
          onCancel={() => cancelTo(mode === 'edit' && scenarioId ? `/scenarios/${scenarioId}` : '/')}
        />

        <section className="panel test-tray" aria-labelledby="available-tests-tray">
          <div className="panel-head">
            <h2 id="available-tests-tray">Available tests</h2>
            <button type="button" className="ghost" onClick={() => void load()}>
              Refresh
            </button>
          </div>
          <p className="muted tight">Drag a compact chip into the scenario drop zone above.</p>
          {tests.length === 0 ? (
            <p className="muted">No tests yet. Start the executor so it can register its catalog.</p>
          ) : (
            <ul className="test-tray-list">
              {tests.map((test) => (
                <li
                  key={test.id}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData('text/test-id', test.id)
                    event.dataTransfer.effectAllowed = 'copy'
                  }}
                  className="test-chip"
                  title={`${test.name} · ${test.steps.join(' → ') || 'no steps'}`}
                >
                  <strong>{test.name}</strong>
                  <span>{test.id}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="page-foot-actions">
        <button type="button" className="ghost" onClick={() => back('/')}>
          Back
        </button>
      </div>
    </div>
  )
}
