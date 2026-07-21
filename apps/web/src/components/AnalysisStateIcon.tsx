/** Small inline SVGs — analyzed vs not-analyzed (document metaphor). */

export function IconAnalyzed({ title = 'Analyzed' }: { title?: string }) {
  return (
    <svg
      className="analysis-state-icon analyzed"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      aria-label={title}
      role="img"
    >
      <title>{title}</title>
      <path
        fill="currentColor"
        d="M3 1.5A1.5 1.5 0 0 1 4.5 0h5.586a1.5 1.5 0 0 1 1.06.44l1.414 1.414A1.5 1.5 0 0 1 13 2.914V14.5A1.5 1.5 0 0 1 11.5 16h-7A1.5 1.5 0 0 1 3 14.5v-13zM4.5 1a.5.5 0 0 0-.5.5v13a.5.5 0 0 0 .5.5h7a.5.5 0 0 0 .5-.5V3H9.5A1.5 1.5 0 0 1 8 1.5V1H4.5zm4 0v.5a.5.5 0 0 0 .5.5H12l-2.5-2.5H9z"
      />
      <path
        fill="currentColor"
        d="M6.2 9.3a.75.75 0 0 1 1.06 0L8.5 10.54l2.24-2.24a.75.75 0 1 1 1.06 1.06l-2.77 2.77a.75.75 0 0 1-1.06 0L6.2 10.36a.75.75 0 0 1 0-1.06z"
      />
    </svg>
  )
}

export function IconNotAnalyzed({ title = 'Not analyzed' }: { title?: string }) {
  return (
    <svg
      className="analysis-state-icon not-analyzed"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      aria-label={title}
      role="img"
    >
      <title>{title}</title>
      <path
        fill="currentColor"
        fillOpacity="0.55"
        d="M3 1.5A1.5 1.5 0 0 1 4.5 0h5.586a1.5 1.5 0 0 1 1.06.44l1.414 1.414A1.5 1.5 0 0 1 13 2.914V14.5A1.5 1.5 0 0 1 11.5 16h-7A1.5 1.5 0 0 1 3 14.5v-13zM4.5 1a.5.5 0 0 0-.5.5v13a.5.5 0 0 0 .5.5h7a.5.5 0 0 0 .5-.5V3H9.5A1.5 1.5 0 0 1 8 1.5V1H4.5zm4 0v.5a.5.5 0 0 0 .5.5H12l-2.5-2.5H9z"
      />
      <circle cx="8" cy="10" r="1.1" fill="currentColor" fillOpacity="0.55" />
      <path
        fill="currentColor"
        fillOpacity="0.55"
        d="M7.25 5.75a.75.75 0 0 1 .75-.75h.01a2 2 0 0 1 1.4 3.43L9 9v.25a.75.75 0 0 1-1.5 0V8.6c0-.3.12-.58.34-.78L8.4 7.3A.5.5 0 0 0 8.01 6.5H8a.75.75 0 0 1-.75-.75z"
      />
    </svg>
  )
}

export function AnalysisSpinner({ title = 'Analyzing…' }: { title?: string }) {
  return <span className="analysis-spinner" title={title} aria-label={title} role="status" />
}
