from datetime import UTC, datetime
from uuid import uuid4

from bia.evals.artifacts import (
    EvalCase,
    EvalCaseOrigin,
    EvalCaseOutcome,
    EvalReport,
    EvalResult,
    EvalVerdict,
    MonitoredRun,
)
from bia.evals.monitoring import _build_drift_report


def _reviewed(passed: int, failed: int) -> list[MonitoredRun]:
    """Builds reviewed runs.

    Args:
        passed: How many the judge approved.
        failed: How many it rejected.

    Returns:
        list[MonitoredRun]: the runs.
    """
    verdicts = [EvalVerdict.PASS] * passed + [EvalVerdict.FAIL] * failed
    return [
        MonitoredRun(
            run_id=uuid4(),
            agent_version_id=uuid4(),
            input="Pregunta",
            output="Respuesta",
            verdict=verdict,
            score=90 if verdict is EvalVerdict.PASS else 10,
            reason="Motivo",
        )
        for verdict in verdicts
    ]


def _baseline(pass_percent: float, has_results: bool) -> EvalReport:
    """Builds the standing of the active version against its cases.

    Args:
        pass_percent: The share of cases it passes.
        has_results: Whether any case has been evaluated.

    Returns:
        EvalReport: the report, with one case.
    """
    now = datetime.now(UTC)
    case = EvalCase(
        id=uuid4(),
        agent_id=uuid4(),
        input="Pregunta",
        expected_behavior="Responde",
        origin=EvalCaseOrigin.MANUAL,
        created_at=now,
    )
    result = EvalResult(
        id=uuid4(),
        eval_case_id=case.id,
        agent_version_id=uuid4(),
        output="Respuesta",
        verdict=EvalVerdict.PASS,
        score=90,
        judge_reason="Motivo",
        created_at=now,
    )
    return EvalReport(
        agent_id=case.agent_id,
        agent_version_id=result.agent_version_id,
        version_number=1,
        threshold_percent=80,
        minimum_cases=8,
        total_cases=1,
        passed_cases=1 if has_results else 0,
        pass_percent=pass_percent,
        minimum_owner_cases=3,
        owner_cases=0,
        passed_owner_cases=0,
        passes_gate=False,
        outcomes=[EvalCaseOutcome(case=case, result=result if has_results else None)],
    )


def test_answers_below_the_threshold_are_drift_with_its_distance_from_the_baseline() -> None:
    """Verifies the report says both whether to worry and how much it got worse."""
    report = _build_drift_report(uuid4(), _reviewed(3, 2), _baseline(90.0, has_results=True))

    assert (report.evaluated_runs, report.passed_runs) == (5, 3)
    assert report.pass_percent == 60.0
    assert report.baseline_pass_percent == 90.0
    assert report.drift_points == 30.0
    assert report.is_drifting is True


def test_answers_at_the_threshold_are_not_drift() -> None:
    """Verifies the same line that lets an agent be published keeps it out of the alarm."""
    report = _build_drift_report(uuid4(), _reviewed(4, 1), _baseline(80.0, has_results=True))

    assert report.drift_points == 0.0
    assert report.is_drifting is False


def test_no_runs_is_not_drift_and_has_no_percentage() -> None:
    """Verifies having nothing to review is not reported as a 0 % agent."""
    report = _build_drift_report(uuid4(), [], _baseline(90.0, has_results=True))

    assert report.pass_percent is None
    assert report.drift_points is None
    assert report.is_drifting is False


def test_a_version_without_results_has_no_baseline() -> None:
    """Verifies a just-edited version is not compared as if it had scored 0 %."""
    report = _build_drift_report(uuid4(), _reviewed(1, 0), _baseline(0.0, has_results=False))

    assert report.baseline_pass_percent is None
    assert report.drift_points is None
