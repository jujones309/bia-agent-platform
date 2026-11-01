from uuid import uuid4

import pytest
from pydantic import ValidationError

from bia.agents.artifacts import AgentSpec


def _spec_values() -> dict[str, object]:
    """Builds the required values of a spec.

    Returns:
        dict[str, object]: the values.
    """
    return {"purpose": "Atender", "system_prompt": "Eres útil", "model_id": str(uuid4())}


def test_spec_defaults_describe_a_limited_agent_without_tools() -> None:
    """Verifies an agent starts with no capabilities beyond those granted and a bounded loop."""
    spec = AgentSpec.model_validate(_spec_values())

    assert spec.tool_names == []
    assert spec.guardrails == []
    assert spec.max_iterations == 5


@pytest.mark.parametrize("max_iterations", [0, 21])
def test_spec_rejects_an_iteration_limit_out_of_range(max_iterations: int) -> None:
    """Verifies a spec can neither prevent all answers nor run up an unbounded cost."""
    with pytest.raises(ValidationError, match="max_iterations"):
        AgentSpec.model_validate({**_spec_values(), "max_iterations": max_iterations})


def test_spec_rejects_unknown_fields() -> None:
    """Verifies a setting the runtime would ignore, like temperature, fails loudly."""
    with pytest.raises(ValidationError, match="temperature"):
        AgentSpec.model_validate({**_spec_values(), "temperature": 0.2})
