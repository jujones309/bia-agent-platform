from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bia.agents.artifacts import AgentDetail, AgentSpec


class DuplicateVerdict(StrEnum):
    """The possible outcomes of checking a new agent request against the registry.

    Produced by `bia/builder/duplicates/` and consumed by the builder API to decide whether to
    ask the user for confirmation or move on to the designer.
    """

    EXISTS = "exists"
    SIMILAR = "similar"  # an agent covers part of the need; the user decides
    NOT_EXISTS = "not_exists"


class AgentRequest(BaseModel):
    """Describes, in natural language, what a person needs an agent for.

    Exists as the body of `POST /builder/check`; consumed by `check_duplicates`.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)


class AgentProposalRequest(AgentRequest):
    """Describes a need together with who will own the agent that covers it.

    Exists as the body of `POST /builder/propose`, because the designer decides the spec but
    cannot know whose agent it is; consumed by `propose_agent`.
    """

    owner_area: str = Field(min_length=1)
    creator: str = Field(min_length=1)


class DuplicateCandidate(BaseModel):
    """Represents a published agent that resembles a need.

    Exists as what the search hands to the judge and what the person is asked to confirm; produced
    by `find_candidates` and returned by `POST /builder/check`.
    """

    agent_id: UUID
    name: str
    description: str
    similarity: float  # cosine similarity between the need and the agent's description


class JudgeDecision(BaseModel):
    """Holds the answer of the duplicate judge, before it is checked against the candidates.

    Exists as the structured output requested from the model, whose strict mode requires every
    field and accepts no defaults. Consumed by `bia/builder/duplicates/judge.py`.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: DuplicateVerdict
    candidate_agent_id: UUID | None  # None only with NOT_EXISTS
    reason: str


class DuplicateCheckResult(BaseModel):
    """Holds the outcome of checking a need against the registry.

    Exists as the contract of `POST /builder/check`; produced by `check_duplicates`.
    """

    verdict: DuplicateVerdict
    candidate: DuplicateCandidate | None  # None only with NOT_EXISTS
    reason: str

    @model_validator(mode="after")
    def _require_candidate_unless_not_exists(self) -> Self:
        """Rejects a verdict that does not fit its candidate.

        Exists because the person is asked to confirm a concrete agent, and cannot confirm one
        that is missing; called by pydantic on construction.

        Returns:
            Self: the validated result.
        """
        if (self.verdict is DuplicateVerdict.NOT_EXISTS) != (self.candidate is None):
            raise ValueError("A candidate is required, unless the verdict is not_exists")
        return self


class DesignerJustification(BaseModel):
    """Explains each decision of a proposed spec.

    Exists so a person can review why the designer chose what it chose, and so the model cannot
    leave a decision unexplained. Produced by the designer and stored in the agent's version.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    tools: str
    knowledge_base: str
    guardrails: str


class AgentDesign(BaseModel):
    """Holds the answer of the designer, before it is validated as a spec.

    Exists as the structured output requested from the model, because the strict mode of the
    provider accepts neither the defaults nor the length limits of `AgentSpec`. Keeping the limits
    out of the wire format also lets a violation reach the designer's retry. Consumed by
    `bia/builder/designer/designer.py`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    system_prompt: str
    model_id: UUID
    tool_names: list[str]
    knowledge_base_id: UUID | None
    guardrails: list[str]
    max_iterations: int
    justification: DesignerJustification


class AgentProposal(BaseModel):
    """Holds a design already validated against the spec rules and the catalogs.

    Exists to tell a usable proposal apart from what the model answered; produced by
    `design_agent` and consumed by `propose_agent`.
    """

    name: str = Field(min_length=1)
    spec: AgentSpec
    justification: DesignerJustification


class ProposedAgent(BaseModel):
    """Holds the draft agent created from a proposal, with the reasons behind it.

    Exists as the contract of `POST /builder/propose`, so the person can review the spec and its
    justification, and adjust it with `PATCH /agents/{id}`; produced by `propose_agent`.
    """

    agent: AgentDetail
    justification: DesignerJustification
