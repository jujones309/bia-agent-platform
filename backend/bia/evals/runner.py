import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.agents.artifacts import AgentStatus
from bia.agents.repository import lock_agent, set_agent_status
from bia.builder.system_agents import EVAL_JUDGE_AGENT_ID
from bia.database.connection import database_session
from bia.evals.artifacts import EvalCase, EvalJudgement, EvalReport, EvalVerdict
from bia.evals.gate import build_report, require_evaluable
from bia.evals.judge import judge_answer
from bia.evals.repository import insert_result, list_cases
from bia.providers.factory import get_provider
from bia.runtime.execution import AgentExecution, load_agent_execution
from bia.runtime.runner import AgentRunner
from bia.tracing.artifacts import RunOrigin
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)

_NO_ANSWER_OUTPUT = ""
_NO_ANSWER_SCORE = 0.0
_NO_ANSWER_REASON = "El agente no produjo una respuesta: {error}"


class NoEvalCasesError(ValueError):
    """Signals that an agent has nothing to be evaluated on.

    Exists so an eval run over nothing is not read as a success. Raised by `run_evals` and
    translated to a 409 by `bia/api/evals.py`.
    """


@dataclass(frozen=True)
class _EvalPlan:
    """Gathers what an eval run needs, read once before the first LLM call.

    Exists so an edit made during the run cannot mix versions in its results; built by
    `_start_eval_run` and consumed by `run_evals`.
    """

    execution: AgentExecution
    judge_execution: AgentExecution
    cases: list[EvalCase]


def _start_eval_run(bind: Engine | Connection, agent_id: UUID) -> _EvalPlan:
    """Prepares an eval run and moves a draft agent to testing.

    Exists to do all the reading in one short transaction; used by `run_evals`.

    Args:
        bind: The database handle to read and write through.
        agent_id: The agent to evaluate.

    Returns:
        _EvalPlan: the version to evaluate, the judge and the cases.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If the agent or the judge has no active version.
        AgentConfigurationError: If a spec references an unavailable model or tool.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        NoEvalCasesError: If the agent has no cases.
    """
    with database_session(bind) as session:
        agent = lock_agent(session, agent_id)
        require_evaluable(agent)
        cases = list_cases(session, agent_id)
        if not cases:
            raise NoEvalCasesError(f"Agent {agent_id} has no eval cases yet")
        plan = _EvalPlan(
            execution=load_agent_execution(session, agent_id),
            judge_execution=load_agent_execution(session, EVAL_JUDGE_AGENT_ID),
            cases=cases,
        )
        if agent.status is AgentStatus.DRAFT:
            set_agent_status(session, agent_id, AgentStatus.TESTING)
    return plan


def _evaluate_case(
    runner: AgentRunner, recorder: RunRecorder, plan: _EvalPlan, case: EvalCase
) -> tuple[str, EvalJudgement]:
    """Runs one case through the real runtime and judges the answer.

    Exists to keep one evaluation apart from the loop over cases. A run without an answer is a fail
    with no judge call: there is nothing to compare, and it would not work for a real user either.

    Args:
        runner: The runtime that executes the agent.
        recorder: Where the judge's trace is written.
        plan: The version to evaluate and the judge.
        case: The case to evaluate.

    Returns:
        tuple[str, EvalJudgement]: the agent's answer and the decision on it.

    Raises:
        ProviderError: If the judge's model call fails.
        InvalidEvalJudgementError: If the answer of the judge is unusable.
    """
    result = runner.run(plan.execution, case.input, RunOrigin.EVAL)
    if result.output is None:
        reason = _NO_ANSWER_REASON.format(error=result.error)
        judgement = EvalJudgement(verdict=EvalVerdict.FAIL, score=_NO_ANSWER_SCORE, reason=reason)
        return _NO_ANSWER_OUTPUT, judgement
    judgement = judge_answer(
        recorder, plan.judge_execution, case.input, case.expected_behavior, result.output
    )
    return result.output, judgement


def run_evals(bind: Engine | Connection, agent_id: UUID) -> EvalReport:
    """Evaluates every case against the active version of an agent, and stores the results.

    Exists as the evidence the publish gate decides on; used by the evals API. Each result commits
    on its own, so no connection stays open during LLM calls and a failure keeps what was done. The
    report is read at the end: if the agent was edited meanwhile, it shows the new version, pending.

    Args:
        bind: The database handle to read, write and trace through.
        agent_id: The agent to evaluate.

    Returns:
        EvalReport: the standing of the active version.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If the agent or the judge has no active version.
        AgentConfigurationError: If a spec references an unavailable model or tool.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        NoEvalCasesError: If the agent has no cases.
        ProviderError: If a call of the judge fails.
        InvalidEvalJudgementError: If an answer of the judge is unusable.
    """
    plan = _start_eval_run(bind, agent_id)
    version = plan.execution.version
    recorder = RunRecorder(bind)
    runner = AgentRunner(recorder, get_provider(plan.execution.model.provider), bind)
    logger.info("Evaluating %d cases on version %d", len(plan.cases), version.version_number)
    for case in plan.cases:
        output, judgement = _evaluate_case(runner, recorder, plan, case)
        with database_session(bind) as session:
            insert_result(session, case.id, version.id, output, judgement)
        logger.info("Case %s judged as %s", case.id, judgement.verdict.value)
    with database_session(bind) as session:
        report = build_report(session, agent_id)
    logger.info("Agent %s stands at %s %% of its cases", agent_id, report.pass_percent)
    return report
