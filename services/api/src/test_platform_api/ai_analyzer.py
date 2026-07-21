"""Optional pydantic-ai backed analyzer — falls back to heuristic when unavailable."""

from __future__ import annotations

import logging
import os

from test_platform_contracts import AnalysisReport

from test_platform_api.analysis import AnalysisContext, HeuristicFailureAnalyzer

logger = logging.getLogger(__name__)


def _has_llm_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANALYSIS_API_KEY"))


def _ensure_openai_env() -> None:
    """pydantic-ai OpenAI provider reads OPENAI_API_KEY; mirror ANALYSIS_API_KEY if needed."""
    if not os.getenv("OPENAI_API_KEY") and os.getenv("ANALYSIS_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["ANALYSIS_API_KEY"]


class PydanticAiFailureAnalyzer:
    """
    Uses pydantic-ai when an API key is configured.
    Falls back to HeuristicFailureAnalyzer on missing key or agent errors.
    """

    def __init__(self) -> None:
        self._fallback = HeuristicFailureAnalyzer()

    def analyze(self, context: AnalysisContext) -> AnalysisReport:
        if not _has_llm_key():
            logger.info("analysis: no API key — using heuristic")
            return self._fallback.analyze(context)
        try:
            _ensure_openai_env()
            logger.info("analysis: calling pydantic-ai agent")
            return self._analyze_with_agent(context)
        except Exception:
            logger.exception("analysis: LLM failed — falling back to heuristic")
            return self._fallback.analyze(context)

    def _analyze_with_agent(self, context: AnalysisContext) -> AnalysisReport:
        from pydantic_ai import Agent

        base = self._fallback.analyze(context)
        agent: Agent[None, AnalysisReport] = Agent(
            os.getenv("ANALYSIS_MODEL", "openai:gpt-4o-mini"),
            output_type=AnalysisReport,
            system_prompt=(
                "You analyze test failures for a test platform. "
                "Return a structured AnalysisReport. "
                "Keep flakiness metrics as provided; do not invent fail rates. "
                "Preserve scenario_name, sut_version, framework_version, infra. "
                "CRITICAL: never invent fingerprints or errors. "
                "If the heuristic draft has errors=[], you MUST return errors=[]. "
                "Only refine errors that already exist in the draft (same fingerprint). "
                "For scope=run or scope=test: ONLY use failures from this run. "
                "For scope=scenario or fingerprint: only use fingerprints present in the draft. "
                "For each error use Given (context/setup), When (full step path to failure), "
                "Then (actual), Expected (intended). "
                "Set root_cause_name, confidence_pct (0-100), error_type "
                "(flake|assertion|timeout|infra|unknown), and components to investigate. "
                "Group the same fingerprint/message across tests into one error with multiple where entries."
            ),
        )
        prompt = (
            f"Scope={context.request.scope.value}\n"
            f"Heuristic draft JSON:\n{base.model_dump_json()}\n"
            "Refine Given/When/Then/Expected, root_cause_name, confidence_pct, "
            "error_type, components, and recommended_actions. "
            "Preserve ids, fingerprints, occurrence counts, when_steps path order, "
            "flakiness, last_failure_run_id, scenario header fields. "
            "Do not add new error entries."
        )
        result = agent.run_sync(prompt)
        refined = result.output
        # All scopes: LLM may only refine existing heuristic fingerprints (never invent).
        if not base.errors:
            errors = []
        else:
            allowed = {e.fingerprint for e in base.errors}
            filtered = [e for e in refined.errors if e.fingerprint in allowed]
            errors = filtered or base.errors
        return refined.model_copy(
            update={
                "id": base.id,
                "scope": base.scope,
                "scenario_id": base.scenario_id,
                "scenario_name": base.scenario_name,
                "run_id": base.run_id,
                "test_id": base.test_id,
                "fingerprint": base.fingerprint,
                "parent_analysis_id": base.parent_analysis_id,
                "sut_version": base.sut_version,
                "framework_version": base.framework_version,
                "infra": base.infra,
                "errors": errors,
                "flakiness": base.flakiness,
                "health_signals": base.health_signals,
                "test_analyses": base.test_analyses,
                "scenario_reliability": base.scenario_reliability,
                "summary": refined.summary if refined.summary else base.summary,
                "generated_at": base.generated_at,
                "contracts_version": base.contracts_version,
            }
        )


def default_analyzer():
    """
    Prefer LLM when a key is present.
    Force heuristic with ANALYSIS_MODE=heuristic; force LLM attempt with ANALYSIS_MODE=pydantic-ai.
    """
    mode = os.getenv("ANALYSIS_MODE", "").lower().strip()
    if mode in {"heuristic", "off", "none"}:
        logger.info("analysis: ANALYSIS_MODE=%s — heuristic", mode or "heuristic")
        return HeuristicFailureAnalyzer()
    if mode in {"pydantic-ai", "pydantic_ai", "llm"} or _has_llm_key():
        logger.info("analysis: using PydanticAiFailureAnalyzer (key present=%s)", _has_llm_key())
        return PydanticAiFailureAnalyzer()
    logger.info("analysis: no key / mode — heuristic")
    return HeuristicFailureAnalyzer()
