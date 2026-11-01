from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, model_validator


class StepType(StrEnum):
    """The kinds of step a run is made of.

    Exists to mirror the `step_type` check of the `run_steps` table; set by the runtime and
    the RAG retrieval when recording a step, and read by the trace views.
    """

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"


class RunStatus(StrEnum):
    """The states of an execution.

    Exists so status comparisons in the recorder and the metrics use a closed set; stored in
    `runs.status` and exposed by the runs API.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunOrigin(StrEnum):
    """What can trigger an execution.

    Exists so the audit record can tell real usage from tests; set by the caller of
    `RunRecorder.start_run` and stored in `runs.origin`.
    """

    PLAYGROUND = "playground"
    EVAL = "eval"
    BUILDER = "builder"
    PRODUCTION = "production"


class RunStepDraft(BaseModel):
    """Describes a step that already happened and is about to be recorded.

    Exists to validate what enters the audit record before it reaches the database; built by
    the runtime and consumed by `RunRecorder.add_step`, which assigns its position.
    """

    step_type: StepType
    model_id: UUID | None = None
    tool_id: UUID | None = None  # stays None if the model asked for a tool that does not exist
    input: JsonValue
    output: JsonValue | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal(0), ge=0)
    latency_ms: int = Field(ge=0)
    error: str | None = None

    @model_validator(mode="after")
    def _require_exactly_one_outcome(self) -> Self:
        """Rejects a step that has both an output and an error, or neither.

        Exists because the data model defines `output` as null only when the step failed;
        called by pydantic on construction.

        Returns:
            Self: the validated step.
        """
        if (self.output is None) == (self.error is None):
            raise ValueError("A run step must have exactly one of output or error")
        return self

    @model_validator(mode="after")
    def _require_model_on_llm_calls(self) -> Self:
        """Rejects an LLM call that does not say which model served it.

        Exists because tokens and cost could not be attributed to a catalog model otherwise;
        called by pydantic on construction.

        Returns:
            Self: the validated step.
        """
        if self.step_type is StepType.LLM_CALL and self.model_id is None:
            raise ValueError("An LLM call step must reference its catalog model")
        return self


class RunStepRecord(BaseModel):
    """Represents one recorded step of a run.

    Exists as the contract of a row of the `run_steps` table; returned by `RunRecorder` and
    nested in `RunRecord` by the runs API.
    """

    id: UUID
    run_id: UUID
    step_order: int
    step_type: StepType
    model_id: UUID | None
    tool_id: UUID | None
    input: JsonValue
    output: JsonValue | None
    input_tokens: int
    output_tokens: int
    cost: Decimal
    latency_ms: int
    error: str | None
    created_at: datetime


class RunRecord(BaseModel):
    """Represents one execution of an agent, with the steps recorded so far.

    Exists as the contract of a row of the `runs` table; returned by `RunRecorder` and by
    the runs API.
    """

    id: UUID
    agent_id: UUID
    agent_version_id: UUID
    origin: RunOrigin
    input: str
    output: str | None
    status: RunStatus
    error: str | None
    total_tokens: int
    total_cost: Decimal
    latency_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[RunStepRecord] = Field(default_factory=list)


class AgentMetrics(BaseModel):
    """Summarizes how an agent has behaved across its runs.

    Exists as the contract of `GET /agents/{id}/metrics`; produced by `get_agent_metrics`.
    """

    agent_id: UUID
    total_runs: int
    total_cost: Decimal
    latency_p50_ms: float | None  # None until a run finishes
    error_rate: float | None  # failed share of finished runs, from 0 to 1; None until one finishes
