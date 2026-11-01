from uuid import uuid4

import pytest
from pydantic import ValidationError

from bia.tracing.artifacts import RunStepDraft, StepType


def test_step_with_an_error_needs_no_output() -> None:
    """Verifies a failed step can be recorded, since failures must reach the audit record."""
    step = RunStepDraft(
        step_type=StepType.TOOL_CALL, input={"a": 1}, error="Unknown tool", latency_ms=0
    )

    assert step.output is None
    assert step.error == "Unknown tool"


@pytest.mark.parametrize(("output", "error"), [(None, None), ({"a": 1}, "boom")])
def test_step_must_have_exactly_one_outcome(
    output: dict[str, int] | None, error: str | None
) -> None:
    """Verifies a step cannot be ambiguous about whether it succeeded."""
    with pytest.raises(ValidationError, match="exactly one of output or error"):
        RunStepDraft(
            step_type=StepType.TOOL_CALL, input={}, output=output, error=error, latency_ms=1
        )


def test_llm_call_must_reference_its_model() -> None:
    """Verifies tokens and cost can always be attributed to a catalog model."""
    with pytest.raises(ValidationError, match="catalog model"):
        RunStepDraft(step_type=StepType.LLM_CALL, input=[], output="hi", latency_ms=1)

    step = RunStepDraft(
        step_type=StepType.LLM_CALL, model_id=uuid4(), input=[], output="hi", latency_ms=1
    )
    assert step.model_id is not None


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cost", "latency_ms"])
def test_step_rejects_negative_measurements(field: str) -> None:
    """Verifies a negative number cannot lower the totals of a run."""
    values: dict[str, object] = {"step_type": StepType.TOOL_CALL, "input": {}, "output": {}}

    with pytest.raises(ValidationError, match=field):
        RunStepDraft.model_validate({"latency_ms": 1, **values, field: -1})
