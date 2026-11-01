import logging
from uuid import UUID

from sqlalchemy.orm import Session

from bia.agents.artifacts import Agent, AgentDetail, AgentKind, AgentStatus
from bia.agents.repository import (
    get_active_version,
    get_agent,
    lock_agent,
    set_agent_status,
)
from bia.evals.artifacts import (
    EvalCaseOrigin,
    EvalCaseOutcome,
    EvalReport,
    EvalVerdict,
    PublishRejection,
)
from bia.evals.config import EVALS_CONFIG
from bia.evals.repository import list_cases, list_latest_results
from bia.orchestrations.flows import register_single_agent_flow

logger = logging.getLogger(__name__)

_FULL_PERCENT = 100
_PERCENT_DECIMALS = 2


class AgentNotEvaluableError(ValueError):
    """Signals that an agent is out of the evals and publishing flow.

    Exists because system agents answer through structured output, which evals do not exercise, and
    archived agents are retired. Raised by `require_evaluable` and translated to a 409 by
    `bia/api/evals.py`.
    """


class PublishRejectedError(ValueError):
    """Signals that the active version of an agent did not pass the gate.

    Exists to carry the detail a person needs to fix it. Raised by `publish_agent` and translated
    to a 409 by `bia/api/evals.py`.
    """

    def __init__(self, rejection: PublishRejection) -> None:
        """Keeps the detail of the rejection.

        Args:
            rejection (PublishRejection): Why the gate refused, with the failing cases.
        """
        super().__init__(rejection.message)
        self.rejection = rejection


def require_evaluable(agent: Agent) -> None:
    """Rejects an agent that cannot go through evals or be published.

    Exists as the shared guard of generation, eval runs, monitoring and publishing.

    Args:
        agent: The agent to check.

    Returns:
        None: the agent can continue.

    Raises:
        AgentNotEvaluableError: If it is a system agent or it was archived.
    """
    if agent.kind is AgentKind.SYSTEM:
        raise AgentNotEvaluableError(f"Agent {agent.id} is a part of the platform")
    if agent.status is AgentStatus.ARCHIVED:
        raise AgentNotEvaluableError(f"Agent {agent.id} is archived")


def percent_of(part: int, total: int) -> float:
    """Expresses a count as a percentage, for people to read.

    Exists so reports round alike; decisions compare whole numbers with `reaches_threshold`.

    Args:
        part: The count.
        total: What it is a part of; must not be zero.

    Returns:
        float: the percentage, rounded to two decimals.
    """
    return round(part * _FULL_PERCENT / total, _PERCENT_DECIMALS)


def reaches_threshold(part: int, total: int) -> bool:
    """Decides whether a count reaches the threshold of the gate.

    Exists to compare whole numbers, so 8 of 10 is exactly 80 % with no rounding involved; used by
    the gate and the monitoring.

    Args:
        part: The count of passes.
        total: What it is a part of.

    Returns:
        bool: True if the share reaches the threshold.
    """
    return part * _FULL_PERCENT >= EVALS_CONFIG.publish_threshold_percent * total


def build_report(session: Session, agent_id: UUID) -> EvalReport:
    """Measures the active version of an agent against the gate.

    Exists as the only definition of passing, shared by the reports and by publishing. It reads the
    latest result of every current case on that version, so a case without one counts against it,
    and editing the agent starts from zero. The cases of the owner area must also reach the
    threshold on their own, or the generated ones could make up for those that measure usefulness.

    Args:
        session: The open session to read through.
        agent_id: The agent to measure.

    Returns:
        EvalReport: the standing of the active version, case by case.

    Raises:
        ActiveVersionNotFoundError: If the agent does not exist or has no active version.
    """
    version = get_active_version(session, agent_id)
    cases = list_cases(session, agent_id)
    results = list_latest_results(session, version.id)
    outcomes = [EvalCaseOutcome(case=case, result=results.get(case.id)) for case in cases]
    passed = sum(1 for outcome in outcomes if _passed(outcome))
    owner_outcomes = [outcome for outcome in outcomes if _is_from_owner(outcome)]
    passed_owner = sum(1 for outcome in owner_outcomes if _passed(outcome))
    return EvalReport(
        agent_id=agent_id,
        agent_version_id=version.id,
        version_number=version.version_number,
        threshold_percent=EVALS_CONFIG.publish_threshold_percent,
        minimum_cases=EVALS_CONFIG.minimum_cases_to_publish,
        total_cases=len(cases),
        passed_cases=passed,
        pass_percent=percent_of(passed, len(cases)) if cases else 0.0,
        minimum_owner_cases=EVALS_CONFIG.minimum_owner_cases,
        owner_cases=len(owner_outcomes),
        passed_owner_cases=passed_owner,
        passes_gate=(
            len(cases) >= EVALS_CONFIG.minimum_cases_to_publish
            and reaches_threshold(passed, len(cases))
            and len(owner_outcomes) >= EVALS_CONFIG.minimum_owner_cases
            and reaches_threshold(passed_owner, len(owner_outcomes))
        ),
        outcomes=outcomes,
    )


def get_report(session: Session, agent_id: UUID) -> EvalReport:
    """Retrieves the report of an agent, telling an unknown agent apart.

    Exists as the read of `GET /agents/{id}/evals`.

    Args:
        session: The open session to read through.
        agent_id: The agent to measure.

    Returns:
        EvalReport: the standing of its active version.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If it has no active version.
    """
    get_agent(session, agent_id)
    return build_report(session, agent_id)


def _passed(outcome: EvalCaseOutcome) -> bool:
    """Tells whether a case passed on the evaluated version.

    Args:
        outcome: The case with its latest result.

    Returns:
        bool: True if it has a result and the judge approved it.
    """
    return outcome.result is not None and outcome.result.verdict is EvalVerdict.PASS


def _is_from_owner(outcome: EvalCaseOutcome) -> bool:
    """Tells whether a case was written by a person of the owner area.

    Args:
        outcome: The case with its latest result.

    Returns:
        bool: True if a person wrote it.
    """
    return outcome.case.origin is EvalCaseOrigin.MANUAL


def _build_rejection(report: EvalReport) -> PublishRejection:
    """Writes why a report does not pass the gate.

    Args:
        report: The standing of the active version.

    Returns:
        PublishRejection: the numbers, with the cases to fix.
    """
    message = (
        f"Version {report.version_number} passed {report.passed_cases} of {report.total_cases} "
        f"cases ({report.pass_percent} %); publishing needs {report.threshold_percent} % "
        f"over at least {report.minimum_cases} cases. The owner area wrote "
        f"{report.owner_cases} cases and {report.passed_owner_cases} passed; publishing needs "
        f"{report.threshold_percent} % over at least {report.minimum_owner_cases} of them"
    )
    return PublishRejection(
        message=message,
        pass_percent=report.pass_percent,
        threshold_percent=report.threshold_percent,
        total_cases=report.total_cases,
        minimum_cases=report.minimum_cases,
        failing_cases=[outcome for outcome in report.outcomes if not _passed(outcome)],
    )


def publish_agent(session: Session, agent_id: UUID) -> AgentDetail:
    """Publishes an agent, if its active version passes the gate.

    Exists so nothing is published without passing its tests; used by the evals API. It runs nothing
    and costs nothing: it reads the stored results, and the lock keeps an edit from slipping in
    between the check and the publication. The agent gets its own flow in the same transaction, so
    it cannot be published without appearing in the orchestration inventory.

    Args:
        session: The open session whose transaction contains the check and the change.
        agent_id: The agent to publish.

    Returns:
        AgentDetail: the published agent with its active version.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If it has no active version.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        PublishRejectedError: If the active version does not pass the gate.
    """
    require_evaluable(lock_agent(session, agent_id))
    report = build_report(session, agent_id)
    if not report.passes_gate:
        logger.info("Gate rejected agent %s at %s %%", agent_id, report.pass_percent)
        raise PublishRejectedError(_build_rejection(report))
    agent = set_agent_status(session, agent_id, AgentStatus.PUBLISHED)
    register_single_agent_flow(session, agent)
    logger.info("Agent %s published at version %d", agent_id, report.version_number)
    return AgentDetail(agent=agent, active_version=get_active_version(session, agent_id))
