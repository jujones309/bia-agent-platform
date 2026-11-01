from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_MAX_ITERATIONS = 5
_ITERATIONS_CEILING = 20


class AgentStatus(StrEnum):
    """The stages of an agent's lifecycle.

    Exists to mirror the `status` check of the `agents` table; set by the registry when an
    agent is created and consumed by the inventories, the duplicate search and the publish gate.
    """

    DRAFT = "draft"
    TESTING = "testing"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AgentKind(StrEnum):
    """Who an agent belongs to.

    Exists to mirror the `kind` check of the `agents` table, so the inventories can tell the
    agents of employees from the parts of the platform; set by the registry.
    """

    USER = "user"  # created by an employee
    SYSTEM = "system"  # part of the platform, like the builder's judge


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


class AgentSpecPatch(BaseModel):
    """Describes the fields of a spec to change; those left out keep their current value.

    Exists as the body of `PATCH /agents/{id}`, so a small adjustment does not require sending
    the whole spec. Holds no constraints of its own: `merge_spec_patch` validates the resulting
    `AgentSpec`, which stays the only definition of a valid spec.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    system_prompt: str | None = None
    model_id: UUID | None = None
    tool_names: list[str] | None = None
    knowledge_base_id: UUID | None = None  # an explicit null detaches the knowledge base
    guardrails: list[str] | None = None
    max_iterations: int | None = None


class AgentDraft(BaseModel):
    """Describes an agent to be created, with the spec of its first version.

    Exists as the body of `POST /agents`; consumed by `create_agent`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owner_area: str = Field(min_length=1)
    creator: str = Field(min_length=1)
    spec: AgentSpec


class Agent(BaseModel):
    """Represents the stable identity of an agent, whatever its version.

    Exists as the contract of a row of the `agents` table, without the embedding, which only
    the duplicate search reads. Returned by the repository and by the agents API.
    """

    id: UUID
    name: str
    description: str
    owner_area: str
    creator: str
    status: AgentStatus
    kind: AgentKind
    active_version_number: int | None  # None only for rows that were created by hand
    created_at: datetime
    updated_at: datetime


class AgentVersion(BaseModel):
    """Represents one immutable version of an agent's spec.

    Exists as the contract of a row of the `agent_versions` table; returned by the repository,
    consumed by the runtime and exposed by the agents API.
    """

    id: UUID
    agent_id: UUID
    version_number: int
    spec: AgentSpec
    designer_justification: str | None
    created_at: datetime


class AgentDetail(BaseModel):
    """Gathers an agent with the version it currently executes.

    Exists so one response shows what the agent is and how it behaves right now; returned by
    the agents API when reading, creating or changing an agent.
    """

    agent: Agent
    active_version: AgentVersion | None  # None only for rows that were created by hand
