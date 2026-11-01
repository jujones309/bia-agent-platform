import pytest

from bia.evals.artifacts import CaseScope, GeneratedCase, GeneratedCases
from bia.evals.cases import NoUsableCasesError, _validate_generated


def _generated(in_scope: int, out_of_scope: int) -> GeneratedCases:
    """Builds an answer of the generator.

    Args:
        in_scope: How many cases are inside the agent's job.
        out_of_scope: How many are outside it.

    Returns:
        GeneratedCases: the answer.
    """
    scopes = [CaseScope.IN_SCOPE] * in_scope + [CaseScope.OUT_OF_SCOPE] * out_of_scope
    return GeneratedCases(
        cases=[
            GeneratedCase(input=f"Pregunta {i}", expected_behavior="Responde", scope=scope)
            for i, scope in enumerate(scopes)
        ]
    )


@pytest.mark.parametrize(("in_scope", "out_of_scope"), [(7, 1), (8, 2)])
def test_sets_within_the_limits_are_accepted(in_scope: int, out_of_scope: int) -> None:
    """Verifies both ends of the agreed range of 8 to 10 cases are valid."""
    _validate_generated(_generated(in_scope, out_of_scope))


@pytest.mark.parametrize(("in_scope", "out_of_scope"), [(6, 1), (9, 2), (0, 0)])
def test_sets_outside_the_limits_are_rejected(in_scope: int, out_of_scope: int) -> None:
    """Verifies a set too small to measure, or larger than was paid for, is not stored."""
    with pytest.raises(NoUsableCasesError, match="cases, not 8 to 10"):
        _validate_generated(_generated(in_scope, out_of_scope))


def test_a_set_without_out_of_scope_cases_is_rejected() -> None:
    """Verifies an agent cannot pass without being tested on what it must decline."""
    with pytest.raises(NoUsableCasesError, match="out of scope"):
        _validate_generated(_generated(9, 0))


def test_a_case_with_an_empty_text_is_rejected() -> None:
    """Verifies blank text, which strict structured output allows, does not reach the runtime."""
    generated = _generated(8, 1)
    generated.cases[0].expected_behavior = "  "

    with pytest.raises(NoUsableCasesError, match="empty text"):
        _validate_generated(generated)
