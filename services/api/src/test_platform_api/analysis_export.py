"""Export analysis report as Markdown + artifacts ZIP (for Jira / handoff)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

from test_platform_contracts import AnalysisReport, ErrorAnalysisItem

from test_platform_api.paths import artifacts_dir


def report_to_markdown(report: AnalysisReport) -> str:
    lines = [
        f"# Failure analysis — {report.scenario_name or report.scenario_id or 'report'}",
        "",
        f"- **Scope:** {report.scope.value}",
        f"- **Scenario:** {report.scenario_name or '—'} (`{report.scenario_id or '—'}`)",
        f"- **Run:** `{report.run_id or '—'}`",
        f"- **Test:** `{report.test_id or '—'}`",
        f"- **Infra:** {report.infra}",
        f"- **SUT:** {report.sut_version}",
        f"- **Framework:** {report.framework_version}",
        f"- **Generated:** {report.generated_at.isoformat()}",
        (
            f"- **Run outcome:** {report.scenario_reliability}"
            if report.scope.value in {"run", "test"}
            else f"- **Scenario reliability:** {report.scenario_reliability}"
        ),
        f"- **Summary:** {report.summary}",
        "",
    ]
    if report.test_analyses:
        lines.extend(["## Per-test analyses", ""])
        for ref in report.test_analyses:
            lines.append(
                f"- `{ref.test_id}` · analysis `{ref.analysis_id}` · "
                f"{ref.error_count} error(s) · {ref.health_signal_count} health signal(s) — {ref.summary}"
            )
        lines.append("")
    if report.health_signals:
        lines.extend(["## Log health signals", ""])
        for signal in report.health_signals:
            lines.append(
                f"- `{signal.test_id}` · **{signal.kind}** ({signal.severity}) — {signal.message}"
            )
        lines.append("")
    for index, err in enumerate(report.errors, start=1):
        lines.extend(_error_md(index, err))
    if report.flakiness:
        lines.extend(["## Flakiness (history)", ""])
        for item in report.flakiness:
            lines.append(
                f"- `{item.test_id}` · fail_rate {item.fail_rate:.1%} · "
                f"{item.failed_runs}/{item.total_runs} · {item.reliability} · "
                f"SUT {item.sut_version} · FW {item.framework_version}"
            )
        lines.append("")
    return "\n".join(lines)


def _error_md(index: int, err: ErrorAnalysisItem) -> list[str]:
    when = " → ".join(err.when_steps) if err.when_steps else "—"
    return [
        f"## Error {index}: {err.root_cause_name or err.label or err.fingerprint}",
        "",
        f"- **Fingerprint:** `{err.fingerprint}`",
        f"- **Error type:** {err.error_type}",
        f"- **Confidence:** {err.confidence_pct}%",
        f"- **Occurrences:** {err.occurrence_count}",
        f"- **Last failure run:** `{err.last_failure_run_id or '—'}`",
        f"- **Components:** {', '.join(err.components) or '—'}",
        f"- **Likely SUT issue:** {'yes' if err.likely_sut_issue else 'no'}",
        "",
        "### Given",
        err.given or "—",
        "",
        "### When",
        when,
        "",
        "### Then",
        err.then_actual or "—",
        "",
        "### Expected",
        err.expected or "—",
        "",
        "### Recommended actions",
        *([f"- {a}" for a in err.recommended_actions] or ["- —"]),
        "",
        f"**Reproduce:** {err.reproduce_path or '—'}",
        "",
    ]


def build_analysis_export_zip(report: AnalysisReport) -> bytes:
    buffer = BytesIO()
    root = artifacts_dir()
    run_ids = {e.last_failure_run_id for e in report.errors if e.last_failure_run_id}
    if report.run_id:
        run_ids.add(report.run_id)

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.md", report_to_markdown(report))
        zf.writestr("report.json", report.model_dump_json(indent=2))
        for run_id in sorted(run_ids):
            run_dir = root / run_id
            if not run_dir.is_dir():
                continue
            for path in run_dir.rglob("*"):
                if path.is_file():
                    arc = Path("artifacts") / run_id / path.relative_to(run_dir)
                    zf.write(path, arcname=str(arc).replace("\\", "/"))
    return buffer.getvalue()
