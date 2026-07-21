import { useState } from 'react'
import { isTestLogDocument, type LogDocument, type LogNode } from '../api'
import { formatTime } from '../lib/format'

export const LOG_LAYERS = ['domain', 'adapter', 'framework'] as const

function flattenNodes(nodes: LogNode[], stepId: string): Array<{ node: LogNode; stepId: string }> {
  return nodes.flatMap((node) => [
    { node, stepId },
    ...flattenNodes(node.children ?? [], stepId),
  ])
}

export function buildConsoleText(document: LogDocument, layers?: Set<string>): string {
  const steps = isTestLogDocument(document) ? document.steps : [document]
  return steps
    .flatMap((step) => flattenNodes(step.entries, step.step_id))
    .filter(({ node }) => !layers || layers.has(node.layer))
    .sort((a, b) => a.node.timestamp.localeCompare(b.node.timestamp))
    .map(({ node, stepId }) => {
      const source = `${node.component ?? 'test'}.${node.layer}`
      const duration = node.duration_ms == null ? '' : ` ${node.duration_ms}ms`
      return `${node.timestamp} ${source} ${node.level.toUpperCase()} [${stepId}] ${node.message}${duration}`
    })
    .join('\n')
}

export function collectLayers(nodes: LogNode[], into: Set<string> = new Set()): Set<string> {
  for (const node of nodes) {
    into.add(node.layer)
    if (node.children?.length) collectLayers(node.children, into)
  }
  return into
}

export function LogTreeNode({
  node,
  depth,
  collapsed,
  onToggle,
  visibleLayers,
}: {
  node: LogNode
  depth: number
  collapsed: Set<string>
  onToggle: (key: string) => void
  visibleLayers: Set<string>
}) {
  if (!visibleLayers.has(node.layer)) return null
  const key = `${depth}:${node.timestamp}:${node.message}:${node.event ?? ''}`
  const hasChildren = (node.children?.length ?? 0) > 0
  const isCollapsed = collapsed.has(key)
  const visibleChildren = (node.children ?? []).filter((child) => {
    // keep parent path if any descendant matches a visible layer
    const layers = collectLayers([child])
    return [...layers].some((layer) => visibleLayers.has(layer))
  })

  return (
    <li className={`log-node layer-${node.layer}`}>
      <div className="log-row" style={{ paddingLeft: `${depth * 0.9}rem` }}>
        {hasChildren ? (
          <button type="button" className="ghost log-toggle" onClick={() => onToggle(key)}>
            {isCollapsed ? '+' : '−'}
          </button>
        ) : (
          <span className="log-toggle-spacer" />
        )}
        <span className={`log-layer chip-${node.layer}`}>{node.layer}</span>
        <span className="log-time">{formatTime(node.timestamp)}</span>
        <span className="log-message">{node.message}</span>
        {node.component ? <span className="muted log-meta">{node.component}</span> : null}
        {node.event ? <span className="muted log-meta">{node.event}</span> : null}
      </div>
      {node.data && Object.keys(node.data).length > 0 && !isCollapsed ? (
        <pre className="log-data" style={{ marginLeft: `${depth * 0.9 + 1.4}rem` }}>
          {JSON.stringify(node.data, null, 2)}
        </pre>
      ) : null}
      {hasChildren && !isCollapsed && visibleChildren.length > 0 ? (
        <ul className="log-children">
          {visibleChildren.map((child, index) => (
            <LogTreeNode
              key={`${key}-c-${index}`}
              node={child}
              depth={depth + 1}
              collapsed={collapsed}
              onToggle={onToggle}
              visibleLayers={visibleLayers}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export function downloadLogJson(document: LogDocument, title: string) {
  const safe = title.replace(/[^\w.-]+/g, '_').slice(0, 80) || 'logs'
  const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = `${safe}.json`
  link.click()
  URL.revokeObjectURL(url)
}

export function downloadConsoleText(document: LogDocument, title: string) {
  const safe = title.replace(/[^\w.-]+/g, '_').slice(0, 80) || 'console'
  const blob = new Blob([`${buildConsoleText(document)}\n`], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = `${safe}.txt`
  link.click()
  URL.revokeObjectURL(url)
}

export function StepLogViewer({
  title,
  document,
  error,
  onClose,
}: {
  title: string
  document: LogDocument | null
  error: string | null
  onClose: () => void
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set())
  const [view, setView] = useState<'console' | 'structured'>('console')

  const stepBlocks = document
    ? isTestLogDocument(document)
      ? document.steps
      : [document]
    : []
  const allEntries = stepBlocks.flatMap((s) => s.entries)
  const availableLayers = allEntries.length
    ? [...collectLayers(allEntries)].sort()
    : [...LOG_LAYERS]
  const visibleLayers = new Set(availableLayers.filter((layer) => !hiddenLayers.has(layer)))

  const toggleCollapsed = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleLayer = (layer: string) => {
    setHiddenLayers((prev) => {
      const next = new Set(prev)
      if (next.has(layer)) next.delete(layer)
      else next.add(layer)
      return next
    })
  }

  const subtitle = document
    ? isTestLogDocument(document)
      ? `Test ${document.test_id ?? '—'} · ${document.steps.length} step(s) (includes pass + fail)`
      : `Step ${document.step_id} · ${document.status}`
    : null

  return (
    <div className="log-viewer">
      <div className="log-viewer-header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="muted tight">{subtitle}</p> : null}
        </div>
        <div className="row-actions">
          <button
            type="button"
            className="ghost"
            disabled={!document}
            onClick={() => document && downloadConsoleText(document, title)}
          >
            Download TXT
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!document}
            onClick={() => document && downloadLogJson(document, title)}
          >
            Download JSON
          </button>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      <div className="log-filters" aria-label="Filter log layers">
        <button type="button" className="ghost" onClick={() => setView('console')}>
          Console
        </button>
        <button type="button" className="ghost" onClick={() => setView('structured')}>
          Structured
        </button>
        <span className="muted">Layers:</span>
        {availableLayers.map((layer) => {
          const on = !hiddenLayers.has(layer)
          return (
            <button
              key={layer}
              type="button"
              className={`ghost log-filter ${on ? 'on' : 'off'}`}
              onClick={() => toggleLayer(layer)}
            >
              {on ? 'Hide' : 'Show'} {layer}
            </button>
          )
        })}
        <button type="button" className="ghost" onClick={() => setCollapsed(new Set())}>
          Expand all
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            if (!document) return
            const keys = new Set<string>()
            const walk = (nodes: LogNode[], depth: number) => {
              for (const node of nodes) {
                const key = `${depth}:${node.timestamp}:${node.message}:${node.event ?? ''}`
                if (node.children?.length) keys.add(key)
                if (node.children) walk(node.children, depth + 1)
              }
            }
            for (const block of stepBlocks) walk(block.entries, 0)
            setCollapsed(keys)
          }}
        >
          Collapse all
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {!document && !error ? <p className="muted">Loading logs…</p> : null}
      {document && view === 'console' ? (
        <pre className="console-output">{buildConsoleText(document, visibleLayers) || 'No log entries.'}</pre>
      ) : null}
      {document && view === 'structured' ? (
        stepBlocks.length === 0 ? (
          <p className="muted tight">No log entries yet.</p>
        ) : (
          <div className="log-step-blocks">
            {stepBlocks.map((block) => (
              <div key={`${block.step_id}-${block.status}`} className="log-step-block">
                <p className="tight">
                  <strong>{block.step_id}</strong>{' '}
                  <span className={`status status-${block.status === 'success' ? 'finished' : 'failed'}`}>
                    {block.status}
                  </span>
                </p>
                {block.entries.length === 0 ? (
                  <p className="muted tight">No entries for this step.</p>
                ) : (
                  <ul className="log-tree">
                    {block.entries.map((node, index) => (
                      <LogTreeNode
                        key={`${block.step_id}-${index}`}
                        node={node}
                        depth={0}
                        collapsed={collapsed}
                        onToggle={toggleCollapsed}
                        visibleLayers={visibleLayers}
                      />
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}
