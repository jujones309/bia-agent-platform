from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseOrigin(StrEnum):
    """How a test case was created.

    Exists to mirror the `origin` check of the `eval_cases` table; set by `bia/evals/cases.py`.
    """

    GENERATED = "generated"
    MANUAL = "manual"


class EvalVerdict(StrEnum):
    """The decisions of the eval judge.

    Exists so the gate and the monitoring compare against a closed set; stored in
    `eval_results.verdict`.
    """

    PASS = "pass"
    FAIL = "fail"


class CaseScope(StrEnum):
    """Whether a generated case falls inside what the agent must solve.

    Exists so generation can prove it covered out-of-scope requests; consumed by
    `bia/evals/cases.py`, and not stored because the expected behavior already says it.
    """

    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"  # the agent must decline without inventing an answer


class EvalCaseDraft(BaseModel):
    """Describes a test case written by a person.

    Exists as the body of `POST /agents/{id}/eval-cases`; consumed by `add_manual_case`.
    """

    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)


class GeneratedCase(BaseModel):
    """Holds one case as the generator wrote it.

    Exists as part of the structured output requested from the model; consumed by
    `bia/evals/cases.py`, which validates it, since strict mode accepts no length limits.
    """

    model_config = ConfigDict(extra="forbid")

    input: str
    expected_behavior: str
    scope: CaseScope


class GeneratedCases(BaseModel):
    """Holds the answer of the case generator.

    Exists as the structured output requested from the model; consumed by `bia/evals/cases.py`.
    """

    model_config = ConfigDict(extra="forbid")

    cases: list[GeneratedCase]


class EvalCase(BaseModel):
    """Represents one stored test case of an agent.

    Exists as the contract of a row of the `eval_cases` table; returned by the repository and the
    evals API.
    """

    id: UUID
    agent_id: UUID
    input: str
    expected_behavior: str
    origin: EvalCaseOrigin
    created_at: datetime


class EvalJudgement(BaseModel):
    """Holds the answer of the eval judge, before it is checked.

    Exists as the structured output requested from the model; consumed by `bia/evals/judge.py`,
    which rejects a score out of range or one that contradicts the verdict.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: EvalVerdict
    score: float
    reason: str


class EvalResult(BaseModel):
    """Represents the outcome of evaluating one case against one version.

    Exists as the contract of a row of the `eval_results` table; returned by the repository and
    nested in `EvalReport`.
    """

    id: UUID
    eval_case_id: UUID
    agent_version_id: UUID
    output: str
    verdict: EvalVerdict
    score: float
    judge_reason: str
    created_at: datetime


class EvalCaseOutcome(BaseModel):
    """Gathers a case with its latest result on the evaluated version.

    Exists so a report shows what was asked next to what happened; nested in `EvalReport`.
    """

    case: EvalCase
    result: EvalResult | None  # None until an eval run reaches this case on this version


class EvalReport(BaseModel):
    """Summarizes how the active version of an agent stands against the publish gate.

    Exists as the contract of `GET /agents/{id}/evals` and `POST /agents/{id}/evals/run`, and as
    what the gate decides on; produced by `build_report`.
    """

    agent_id: UUID
    agent_version_id: UUID
    version_number: int
    threshold_percent: int
    minimum_cases: int
    total_cases: int
    passed_cases: int
    pass_percent: float  # over every case, so a case without a result counts against the gate
    passes_gate: bool
    outcomes: list[EvalCaseOutcome]


class PublishRejection(BaseModel):
    """Explains why the gate refused to publish an agent.

    Exists as the body of the 409 of `POST /agents/{id}/publish`, so a person can see what to fix;
    built by `publish_agent`.
    """

    message: str
    pass_percent: float
    threshold_percent: int
    total_cases: int
    minimum_cases: int
    failing_cases: list[EvalCaseOutcome]  # failed, or without a result on the active version


class MonitoredRun(BaseModel):
    """Holds the judge's opinion on one real run.

    Exists so a drift report points at the concrete answers it objects to; nested in `DriftReport`.
    """

    run_id: UUID
    agent_version_id: UUID
    input: str
    output: str
    verdict: EvalVerdict
    score: float
    reason: str


class DriftReport(BaseModel):
    """Compares recent real answers of an agent with what it achieved before being published.

    Exists as the contract of `POST /agents/{id}/evals/monitor`; produced by `monitor_agent`.
    """

    agent_id: UUID
    evaluated_runs: int
    passed_runs: int
    pass_percent: float | None  # None when there was no run to evaluate
    baseline_pass_percent: float | None  # None when the active version has no evaluated case
    drift_points: float | None  # baseline minus recent; positive means it got worse
    threshold_percent: int
    is_drifting: bool  # the recent answers fall below the threshold of the gate
    runs: list[MonitoredRun]
