import json
import logging
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.agents.artifacts import AgentSpec
from bia.agents.repository import get_agent, list_versions
from bia.builder.system_agents import EVAL_JUDGE_AGENT_ID
from bia.database.connection import database_session
from bia.evals.artifacts import DriftReport, EvalReport, EvalVerdict, MonitoredRun
from bia.evals.config import EVALS_CONFIG
from bia.evals.gate import build_report, percent_of, reaches_threshold, require_evaluable
from bia.evals.judge import judge_answer
from bia.runtime.execution import AgentExecution, load_agent_execution
from bia.tracing.artifacts import RunOrigin, RunRecord
from bia.tracing.recorder import RunRecorder
from bia.tracing.repository import list_succeeded_runs

logger = logging.getLogger(__name__)


def _expected_from_spec(spec: AgentSpec) -> str:
    """Writes what a real run should have done, from the spec that served it.

    Exists because real runs have no test case behind them; used by `_judge_run`.

    Args:
        spec: The version that answered.

    Returns:
        str: a JSON document with the purpose and the rules of the agent.
    """
    return json.dumps({"proposito": spec.purpose, "reglas": spec.guardrails}, ensure_ascii=False)


def _judge_run(
    recorder: RunRecorder, judge_execution: AgentExecution, run: RunRecord, spec: AgentSpec
) -> MonitoredRun:
    """Asks the eval judge about one real run.

    Exists to keep one evaluation apart from the loop over runs; used by `monitor_agent`.

    Args:
        recorder: Where the judge's trace is written.
        judge_execution: The active version of the eval judge.
        run: The run to review.
        spec: The version that served it.

    Returns:
        MonitoredRun: the run with the opinion of the judge.

    Raises:
        ProviderError: If the model call fails.
        InvalidEvalJudgementError: If the answer of the judge is unusable.
    """
    judgement = judge_answer(
        recorder, judge_execution, run.input, _expected_from_spec(spec), run.output
    )
    return MonitoredRun(
        run_id=run.id,
        agent_version_id=run.agent_version_id,
        input=run.input,
        output=run.output,
        verdict=judgement.verdict,
        score=judgement.score,
        reason=judgement.reason,
    )


def _build_drift_report(
    agent_id: UUID, reviewed: list[MonitoredRun], baseline: EvalReport
) -> DriftReport:
    """Compares the reviewed runs with what the active version achieved in its evals.

    Exists to keep the arithmetic apart from the calls; used by `monitor_agent`.

    Args:
        agent_id: The agent reviewed.
        reviewed: The runs with the opinion of the judge.
        baseline: The standing of the active version against its cases.

    Returns:
        DriftReport: the comparison, with the runs.
    """
    passed = sum(1 for entry in reviewed if entry.verdict is EvalVerdict.PASS)
    recent = percent_of(passed, len(reviewed)) if reviewed else None
    has_baseline = any(outcome.result is not None for outcome in baseline.outcomes)
    baseline_percent = baseline.pass_percent if has_baseline else None
    has_both = recent is not None and baseline_percent is not None
    return DriftReport(
        agent_id=agent_id,
        evaluated_runs=len(reviewed),
        passed_runs=passed,
        pass_percent=recent,
        baseline_pass_percent=baseline_percent,
        drift_points=round(baseline_percent - recent, 2) if has_both else None,
        threshold_percent=EVALS_CONFIG.publish_threshold_percent,
        is_drifting=bool(reviewed) and not reaches_threshold(passed, len(reviewed)),
        runs=reviewed,
    )


def monitor_agent(
    bind: Engine | Connection, agent_id: UUID, origin: RunOrigin, sample_size: int
) -> DriftReport:
    """Reviews the most recent real answers of an agent with the eval judge, and reports drift.

    Exists because passing before publishing says nothing about what happens later; used by the
    evals API. It writes no results and changes no status: a person decides what to do. Each review
    is traced as a run of the judge, so no connection stays open during LLM calls.

    Args:
        bind: The database handle to read and trace through.
        agent_id: The agent to review.
        origin: Which runs to sample.
        sample_size: How many of its most recent answered runs to review.

    Returns:
        DriftReport: how the recent answers compare with the gate and the evals.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If the agent or the judge has no active version.
        AgentConfigurationError: If the judge references an unavailable model.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        ProviderError: If a call of the judge fails.
        InvalidEvalJudgementError: If an answer of the judge is unusable.
    """
    with database_session(bind) as session:
        require_evaluable(get_agent(session, agent_id))
        judge_execution = load_agent_execution(session, EVAL_JUDGE_AGENT_ID)
        runs = list_succeeded_runs(session, agent_id, origin, sample_size)
        specs = {version.id: version.spec for version in list_versions(session, agent_id)}
        baseline = build_report(session, agent_id)
    recorder = RunRecorder(bind)
    reviewed = [
        _judge_run(recorder, judge_execution, run, specs[run.agent_version_id]) for run in runs
    ]
    report = _build_drift_report(agent_id, reviewed, baseline)
    logger.info(
        "Reviewed %d %s runs of agent %s: %s %%",
        len(reviewed),
        origin.value,
        agent_id,
        report.pass_percent,
    )
    return report
