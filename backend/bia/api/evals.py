from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentDetail
from bia.agents.repository import ActiveVersionNotFoundError, AgentNotFoundError
from bia.api.dependencies import get_database_engine, get_session
from bia.evals.artifacts import DriftReport, EvalCase, EvalCaseDraft, EvalReport
from bia.evals.cases import (
    CasesAlreadyGeneratedError,
    NoUsableCasesError,
    add_manual_case,
    generate_cases,
    remove_case,
)
from bia.evals.gate import (
    AgentNotEvaluableError,
    PublishRejectedError,
    get_report,
    publish_agent,
)
from bia.evals.judge import InvalidEvalJudgementError
from bia.evals.monitoring import monitor_agent
from bia.evals.repository import EvalCaseNotFoundError
from bia.evals.runner import NoEvalCasesError, run_evals
from bia.providers.base import ProviderError
from bia.runtime.execution import AgentConfigurationError
from bia.tracing.artifacts import RunOrigin

_DEFAULT_MONITOR_SAMPLE = 10
_MAX_MONITOR_SAMPLE = 50

router = APIRouter(prefix="/agents/{agent_id}", tags=["evals"])


@router.post("/eval-cases", response_model=EvalCase, status_code=status.HTTP_201_CREATED)
def post_eval_case(
    agent_id: UUID,
    draft: EvalCaseDraft,
    session: Annotated[Session, Depends(get_session)],
) -> EvalCase:
    """Adds a test case written by a person.

    Exists so the owner can test what they know matters; served as
    `POST /agents/{id}/eval-cases`.

    Args:
        agent_id: The agent the case evaluates.
        draft: What to ask and what to expect.
        session: The session of the request.

    Returns:
        EvalCase: the stored case.

    Raises:
        HTTPException: A 404 if the agent does not exist, or a 409 if it cannot be evaluated.
    """
    try:
        return add_manual_case(session, agent_id, draft)
    except AgentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentNotEvaluableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.delete("/eval-cases/{eval_case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_eval_case(
    agent_id: UUID,
    eval_case_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Retires a test case, keeping its past results as history.

    Exists so a badly written case can be removed without SQL; served as
    `DELETE /agents/{id}/eval-cases/{case_id}`.

    Args:
        agent_id: The agent the case belongs to.
        eval_case_id: The case to retire.
        session: The session of the request.

    Returns:
        None: the response has no body.

    Raises:
        HTTPException: A 404 if the agent or the case does not exist, or a 409 if the agent cannot
            be evaluated.
    """
    try:
        remove_case(session, agent_id, eval_case_id)
    except (AgentNotFoundError, EvalCaseNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentNotEvaluableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.post(
    "/eval-cases/generate", response_model=list[EvalCase], status_code=status.HTTP_201_CREATED
)
def post_generate_eval_cases(
    agent_id: UUID, engine: Annotated[Engine, Depends(get_database_engine)]
) -> list[EvalCase]:
    """Writes the test cases of an agent from its active spec.

    Exists so nobody has to know how to test an LLM; served as
    `POST /agents/{id}/eval-cases/generate`. Uses the engine because a request-scoped session would
    stay open during the LLM call.

    Args:
        agent_id: The agent to write cases for.
        engine: The engine to read, write and trace through.

    Returns:
        list[EvalCase]: the stored cases.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist, a 409 if it cannot be
            evaluated, already has generated cases or its spec is stale, or a 502 if the model call
            fails or its answer is unusable.
    """
    try:
        return generate_cases(engine, agent_id)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (
        AgentNotEvaluableError,
        CasesAlreadyGeneratedError,
        AgentConfigurationError,
    ) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (ProviderError, NoUsableCasesError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


@router.post("/evals/run", response_model=EvalReport)
def post_run_evals(
    agent_id: UUID, engine: Annotated[Engine, Depends(get_database_engine)]
) -> EvalReport:
    """Evaluates every case against the active version of an agent.

    Exists as the step that produces the evidence for publishing; served as
    `POST /agents/{id}/evals/run`. Uses the engine because a request-scoped session would stay open
    during the LLM calls. A failure of the agent's own model is a failed case, not a failed request.

    Args:
        agent_id: The agent to evaluate.
        engine: The engine to read, write and trace through.

    Returns:
        EvalReport: the standing of the active version, case by case.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist, a 409 if it cannot be
            evaluated, has no cases or its spec is stale, or a 502 if the judge fails.
    """
    try:
        return run_evals(engine, agent_id)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (AgentNotEvaluableError, NoEvalCasesError, AgentConfigurationError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (ProviderError, InvalidEvalJudgementError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


@router.get("/evals", response_model=EvalReport)
def get_evals(agent_id: UUID, session: Annotated[Session, Depends(get_session)]) -> EvalReport:
    """Reads how the active version of an agent stands, without running anything.

    Exists so a person can review the results as often as they want at no cost; served as
    `GET /agents/{id}/evals`.

    Args:
        agent_id: The agent to measure.
        session: The session of the request.

    Returns:
        EvalReport: the standing of the active version, case by case.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist.
    """
    try:
        return get_report(session, agent_id)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@router.post("/publish", response_model=AgentDetail)
def post_publish(agent_id: UUID, session: Annotated[Session, Depends(get_session)]) -> AgentDetail:
    """Publishes an agent, if its active version passes the gate.

    Exists so nothing is published without passing its tests; served as
    `POST /agents/{id}/publish`.

    Args:
        agent_id: The agent to publish.
        session: The session of the request.

    Returns:
        AgentDetail: the published agent.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist, or a 409 if it cannot be
            evaluated or does not pass, with the failing cases in the detail.
    """
    try:
        return publish_agent(session, agent_id)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentNotEvaluableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except PublishRejectedError as error:
        detail = error.rejection.model_dump(mode="json")
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from error


@router.post("/evals/monitor", response_model=DriftReport)
def post_monitor(
    agent_id: UUID,
    engine: Annotated[Engine, Depends(get_database_engine)],
    origin: RunOrigin = RunOrigin.PRODUCTION,
    sample_size: Annotated[int, Query(ge=1, le=_MAX_MONITOR_SAMPLE)] = _DEFAULT_MONITOR_SAMPLE,
) -> DriftReport:
    """Reviews the most recent real answers of an agent, and reports drift.

    Exists to watch an agent after publishing it; served as `POST /agents/{id}/evals/monitor`, a
    POST because each review pays for a model call. Uses the engine because a request-scoped session
    would stay open during the LLM calls.

    Args:
        agent_id: The agent to review.
        engine: The engine to read and trace through.
        origin: Which runs to sample.
        sample_size: How many of its most recent answered runs to review.

    Returns:
        DriftReport: how the recent answers compare with the gate and the evals.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist, a 409 if it cannot be
            evaluated or the judge's spec is stale, or a 502 if the judge fails.
    """
    try:
        return monitor_agent(engine, agent_id, origin, sample_size)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (AgentNotEvaluableError, AgentConfigurationError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (ProviderError, InvalidEvalJudgementError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
