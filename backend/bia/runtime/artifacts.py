from uuid import UUID

from pydantic import BaseModel, Field

from bia.tracing.artifacts import RunStatus


class AgentRunRequest(BaseModel):
    """Describes the body of a request to execute an agent.

    Exists as the contract of `POST /agents/{id}/run`; consumed by `bia/api/runtime.py`.
    """

    input: str = Field(min_length=1)


class AgentRunResult(BaseModel):
    """Holds the outcome of an agent execution.

    Exists so callers get the answer, or the reason there is none, together with the run
    that traces it. Produced by `AgentRunner` and returned by the playground endpoint.
    """

    run_id: UUID
    status: RunStatus
    output: str | None  # None when the run failed
    error: str | None  # None when the run succeeded
