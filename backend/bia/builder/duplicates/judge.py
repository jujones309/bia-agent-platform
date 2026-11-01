import json
import logging

from sqlalchemy import Connection, Engine

from bia.builder.artifacts import (
    AgentRequest,
    DuplicateCandidate,
    DuplicateCheckResult,
    DuplicateVerdict,
    JudgeDecision,
)
from bia.builder.duplicates.search import find_candidates
from bia.builder.system_agents import DUPLICATE_JUDGE_AGENT_ID
from bia.builder.system_run import SystemAgentRun
from bia.catalog.models.artifacts import CatalogModel
from bia.catalog.models.repository import find_embedding_model
from bia.database.connection import database_session
from bia.runtime.execution import load_agent_execution
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)

_NO_CANDIDATES_REASON = "Todavía no hay agentes publicados con los que comparar esta necesidad."


class InvalidJudgeDecisionError(ValueError):
    """Signals that the judge answered something that does not fit the candidates it received.

    Exists because the person would otherwise be asked to confirm an agent the search never found.
    Raised by `_to_result` and translated to a 502 by `bia/api/builder.py`.
    """


def _to_result(
    decision: JudgeDecision, candidates: list[DuplicateCandidate]
) -> DuplicateCheckResult:
    """Resolves the judge's answer against the candidates it received.

    Exists because the structured output guarantees the shape of the answer, not its truth; used by
    `judge_need`.

    Args:
        decision: The answer of the judge.
        candidates: The candidates it compared.

    Returns:
        DuplicateCheckResult: the verdict with the chosen agent.

    Raises:
        InvalidJudgeDecisionError: If the chosen agent does not fit the verdict or the candidates.
    """
    chosen_id = decision.candidate_agent_id
    if decision.verdict is DuplicateVerdict.NOT_EXISTS:
        if chosen_id is not None:
            raise InvalidJudgeDecisionError(f"The judge chose {chosen_id} but said not_exists")
        return DuplicateCheckResult(
            verdict=decision.verdict, candidate=None, reason=decision.reason
        )
    candidate = next((entry for entry in candidates if entry.agent_id == chosen_id), None)
    if candidate is None:
        raise InvalidJudgeDecisionError(
            f"The judge said {decision.verdict.value} with {chosen_id}, not one of the candidates"
        )
    return DuplicateCheckResult(
        verdict=decision.verdict, candidate=candidate, reason=decision.reason
    )


def _build_judge_input(description: str, candidates: list[DuplicateCandidate]) -> str:
    """Writes the data the judge's prompt expects.

    Exists to keep the need and the candidates apart from the versioned instructions; used by
    `judge_need`.

    Args:
        description: The described need.
        candidates: The candidates to compare.

    Returns:
        str: the JSON document of the user message.
    """
    payload = {
        "necesidad": description,
        "candidatos": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    return json.dumps(payload, ensure_ascii=False)


def judge_need(
    run: SystemAgentRun,
    bind: Engine | Connection,
    description: str,
    embedding_model: CatalogModel,
) -> DuplicateCheckResult:
    """Searches for agents like the described need and decides whether one covers it.

    Exists to combine the search and the judge inside one traced run; used by `check_duplicates`.
    Without candidates there is nothing to judge, so the model is not called.

    Args:
        run: The open run of the judge.
        bind: The database handle to search through.
        description: The described need.
        embedding_model: The model that embeds the need.

    Returns:
        DuplicateCheckResult: the verdict, with the chosen agent if there is one.

    Raises:
        ProviderError: If a model call fails.
        InvalidJudgeDecisionError: If the judge's answer does not fit the candidates.
    """
    logger.info("Searching the registry for agents like the described need")
    embedding = run.embed(description, embedding_model)
    with database_session(bind) as session:
        candidates = find_candidates(session, embedding)
    if not candidates:
        logger.info("No published candidates; skipping the judge")
        return DuplicateCheckResult(
            verdict=DuplicateVerdict.NOT_EXISTS, candidate=None, reason=_NO_CANDIDATES_REASON
        )
    messages = run.initial_messages(_build_judge_input(description, candidates))
    result = _to_result(run.ask(messages, JudgeDecision), candidates)
    logger.info("Judge verdict: %s among %d candidates", result.verdict.value, len(candidates))
    return result


def check_duplicates(bind: Engine | Connection, request: AgentRequest) -> DuplicateCheckResult:
    """Checks whether a need is already covered by a published agent.

    Exists as the first step of the builder, so the platform reuses before it creates; used by the
    builder API. Reads happen in short transactions, so no connection stays open during LLM calls.

    Args:
        bind: The database handle to read and trace through.
        request: The described need.

    Returns:
        DuplicateCheckResult: the verdict, with the chosen agent if there is one.

    Raises:
        ActiveVersionNotFoundError: If the judge is not registered.
        AgentConfigurationError: If the judge's spec references an unavailable model.
        EmbeddingModelUnavailableError: If the catalog has no active embedding model.
        ProviderError: If a model call fails.
        InvalidJudgeDecisionError: If the judge's answer does not fit the candidates.
    """
    with database_session(bind) as session:
        execution = load_agent_execution(session, DUPLICATE_JUDGE_AGENT_ID)
        embedding_model = find_embedding_model(session)
    with SystemAgentRun(RunRecorder(bind), execution, request.description) as run:
        result = judge_need(run, bind, request.description, embedding_model)
        run.finish(result.model_dump_json())
    return result
