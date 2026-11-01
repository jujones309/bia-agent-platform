from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bia.agents.artifacts import Agent, AgentKind, AgentStatus
from bia.evals.gate import (
    AgentNotEvaluableError,
    percent_of,
    reaches_threshold,
    require_evaluable,
)


def _agent(kind: AgentKind, status: AgentStatus) -> Agent:
    """Builds an agent.

    Args:
        kind: Who it belongs to.
        status: The stage of its lifecycle.

    Returns:
        Agent: the agent.
    """
    now = datetime.now(UTC)
    return Agent(
        id=uuid4(),
        name="Asistente",
        description="Facturas",
        owner_area="Servicio",
        creator="Ana",
        status=status,
        kind=kind,
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    ("part", "total", "expected"),
    [(8, 10, True), (7, 10, False), (10, 10, True), (4, 5, True), (79, 100, False), (0, 8, False)],
)
def test_threshold_is_exact_at_80_percent(part: int, total: int, expected: bool) -> None:
    """Verifies reaching exactly the threshold passes, and no rounding helps below it."""
    assert reaches_threshold(part, total) is expected


def test_percent_rounds_for_reading() -> None:
    """Verifies reports show a readable number."""
    assert percent_of(2, 3) == 66.67


@pytest.mark.parametrize(
    ("kind", "status"),
    [(AgentKind.SYSTEM, AgentStatus.PUBLISHED), (AgentKind.USER, AgentStatus.ARCHIVED)],
)
def test_system_and_archived_agents_are_out_of_the_flow(
    kind: AgentKind, status: AgentStatus
) -> None:
    """Verifies money is not spent on evaluating what cannot be published."""
    with pytest.raises(AgentNotEvaluableError):
        require_evaluable(_agent(kind, status))


@pytest.mark.parametrize("status", [AgentStatus.DRAFT, AgentStatus.TESTING, AgentStatus.PUBLISHED])
def test_agents_of_employees_can_go_through_the_flow(status: AgentStatus) -> None:
    """Verifies a published agent can be evaluated again."""
    require_evaluable(_agent(AgentKind.USER, status))
