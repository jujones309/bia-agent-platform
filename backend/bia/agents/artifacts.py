from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_MAX_ITERATIONS = 5
_ITERATIONS_CEILING = 20


class AgentSpec(BaseModel):
    """Declares what an agent is and how it behaves.

    Exists because an agent is versioned configuration and never generated code; stored in
    `agent_versions.spec`, proposed by the designer and executed by `bia/runtime/`. Unknown
    fields are rejected so a misspelled setting fails instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    model_id: UUID  # entry of the model catalog
    tool_names: list[str] = Field(default_factory=list)  # entries of the tool catalog
    knowledge_base_id: UUID | None = None  # not read by the runtime until phase 7 adds retrieval
    guardrails: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=_DEFAULT_MAX_ITERATIONS, ge=1, le=_ITERATIONS_CEILING)


class AgentVersion(BaseModel):
    """Represents one immutable version of an agent's spec.

    Exists as the contract of a row of the `agent_versions` table; returned by
    `get_active_version` and consumed by the runtime.
    """

    id: UUID
    agent_id: UUID
    version_number: int
    spec: AgentSpec
    designer_justification: str | None
    created_at: datetime
