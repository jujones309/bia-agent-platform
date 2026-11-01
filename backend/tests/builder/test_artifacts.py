import json
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from bia.builder.artifacts import (
    AgentDesign,
    DuplicateCandidate,
    DuplicateCheckResult,
    DuplicateVerdict,
    JudgeDecision,
)


def _candidate() -> DuplicateCandidate:
    """Builds a candidate.

    Returns:
        DuplicateCandidate: the candidate.
    """
    return DuplicateCandidate(
        agent_id=uuid4(), name="Asistente", description="Facturas", similarity=0.9
    )


@pytest.mark.parametrize("verdict", [DuplicateVerdict.EXISTS, DuplicateVerdict.SIMILAR])
def test_check_result_requires_the_agent_to_confirm(verdict: DuplicateVerdict) -> None:
    """Verifies the person is never asked to confirm an agent that is missing."""
    with pytest.raises(ValidationError, match="candidate is required"):
        DuplicateCheckResult(verdict=verdict, candidate=None, reason="Razón")


def test_check_result_rejects_a_candidate_on_not_exists() -> None:
    """Verifies a verdict of no duplicate cannot also point at an agent."""
    with pytest.raises(ValidationError, match="candidate is required"):
        DuplicateCheckResult(
            verdict=DuplicateVerdict.NOT_EXISTS, candidate=_candidate(), reason="Razón"
        )


@pytest.mark.parametrize("contract", [JudgeDecision, AgentDesign])
def test_model_answers_use_only_what_the_strict_mode_accepts(contract: type[BaseModel]) -> None:
    """Verifies no default or length limit reaches the provider, which rejects them on the wire."""
    schema = json.dumps(contract.model_json_schema())

    assert '"default"' not in schema
    assert '"minLength"' not in schema
    assert set(contract.model_json_schema()["required"]) == set(contract.model_fields)
