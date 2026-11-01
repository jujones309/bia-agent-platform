import json
import logging
from uuid import UUID

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from bia.agents.repository import get_agent, lock_agent
from bia.builder.system_agents import CASE_GENERATOR_AGENT_ID
from bia.builder.system_run import SystemAgentRun
from bia.database.connection import database_session
from bia.evals.artifacts import (
    CaseScope,
    EvalCase,
    EvalCaseDraft,
    EvalCaseOrigin,
    GeneratedCases,
)
from bia.evals.config import EVALS_CONFIG
from bia.evals.gate import require_evaluable
from bia.evals.repository import insert_case, list_cases, retire_case
from bia.runtime.execution import AgentExecution, load_agent_execution
from bia.tracing.artifacts import RunOrigin
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)


class CasesAlreadyGeneratedError(ValueError):
    """Signals that an agent already has generated cases.

    Exists because generating again would pile up cases and pay for them; retiring every generated
    case allows generating again. Raised by `generate_cases` and translated to a 409 by
    `bia/api/evals.py`.
    """


class NoUsableCasesError(ValueError):
    """Signals that the generator did not write a usable set of cases.

    Exists so a set that would make the gate meaningless is not stored. Raised by `generate_cases`
    and translated to a 502 by `bia/api/evals.py`.
    """


def add_manual_case(session: Session, agent_id: UUID, draft: EvalCaseDraft) -> EvalCase:
    """Adds a case written by a person to an agent.

    Exists so the owner can test what they know matters; used by the evals API.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent the case evaluates.
        draft: What to ask and what to expect.

    Returns:
        EvalCase: the stored case.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        AgentNotEvaluableError: If it is a system agent or it was archived.
    """
    require_evaluable(get_agent(session, agent_id))
    return insert_case(session, agent_id, draft, EvalCaseOrigin.MANUAL)


def remove_case(session: Session, agent_id: UUID, eval_case_id: UUID) -> None:
    """Retires a badly written case of an agent.

    Exists because a wrong case counts against the gate forever otherwise; used by the evals API.
    The lock keeps the removal from slipping in between the check and the change of a publication.
    The gate's minimum of cases still applies to what remains.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent the case belongs to.
        eval_case_id: The case to retire.

    Returns:
        None: the case no longer counts.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        EvalCaseNotFoundError: If the agent has no current case with that identifier.
    """
    require_evaluable(lock_agent(session, agent_id))
    retire_case(session, agent_id, eval_case_id)
    logger.info("Retired eval case %s of agent %s", eval_case_id, agent_id)


def _require_no_generated_cases(session: Session, agent_id: UUID) -> None:
    """Rejects a second generation for an agent.

    Exists as the check made before paying for the model, and again under the lock before writing.

    Args:
        session: The open session to read through.
        agent_id: The agent to check.

    Returns:
        None: the agent has no generated cases.

    Raises:
        CasesAlreadyGeneratedError: If it has some.
    """
    if any(case.origin is EvalCaseOrigin.GENERATED for case in list_cases(session, agent_id)):
        raise CasesAlreadyGeneratedError(f"Agent {agent_id} already has generated cases")


def _build_generator_input(name: str, description: str, execution: AgentExecution) -> str:
    """Writes the data the generator's prompt expects.

    Exists to keep the agent apart from the versioned instructions; used by `generate_cases`.

    Args:
        name: The name of the agent.
        description: The need the agent covers.
        execution: Its active version, with its tools.

    Returns:
        str: the JSON document of the user message.
    """
    spec = execution.version.spec
    payload = {
        "agente": {
            "nombre": name,
            "descripcion": description,
            "proposito": spec.purpose,
            "system_prompt": spec.system_prompt,
            "guardrails": spec.guardrails,
        },
        "herramientas": [
            {"nombre": tool.name, "descripcion": tool.description} for tool in execution.tools
        ],
        "tiene_base_de_conocimiento": spec.knowledge_base_id is not None,
        "cantidad_minima": EVALS_CONFIG.minimum_generated_cases,
        "cantidad_maxima": EVALS_CONFIG.maximum_generated_cases,
    }
    return json.dumps(payload, ensure_ascii=False)


def _validate_generated(generated: GeneratedCases) -> None:
    """Rejects a set of cases that would not measure the agent.

    Exists because strict structured output accepts no length limits; used by `generate_cases`.

    Args:
        generated: The answer of the generator.

    Returns:
        None: the set is usable.

    Raises:
        NoUsableCasesError: If the count is off, a text is empty, or nothing is out of scope.
    """
    cases = generated.cases
    minimum, maximum = EVALS_CONFIG.minimum_generated_cases, EVALS_CONFIG.maximum_generated_cases
    if not minimum <= len(cases) <= maximum:
        raise NoUsableCasesError(f"Generated {len(cases)} cases, not {minimum} to {maximum}")
    if any(not (case.input.strip() and case.expected_behavior.strip()) for case in cases):
        raise NoUsableCasesError("A generated case has an empty text")
    out_of_scope = sum(1 for case in cases if case.scope is CaseScope.OUT_OF_SCOPE)
    if out_of_scope < EVALS_CONFIG.minimum_out_of_scope_cases:
        raise NoUsableCasesError("No generated case is out of scope")


def _store_generated(
    bind: Engine | Connection, agent_id: UUID, generated: GeneratedCases
) -> list[EvalCase]:
    """Stores a generated set, all of it or nothing.

    Exists to take the lock that keeps two concurrent generations from both storing; used by
    `generate_cases`.

    Args:
        bind: The database handle to write through.
        agent_id: The agent the cases evaluate.
        generated: The validated set.

    Returns:
        list[EvalCase]: the stored cases.

    Raises:
        CasesAlreadyGeneratedError: If a concurrent generation stored its set first.
    """
    with database_session(bind) as session:
        lock_agent(session, agent_id)
        _require_no_generated_cases(session, agent_id)
        return [
            insert_case(
                session,
                agent_id,
                EvalCaseDraft(input=case.input, expected_behavior=case.expected_behavior),
                EvalCaseOrigin.GENERATED,
            )
            for case in generated.cases
        ]


def generate_cases(bind: Engine | Connection, agent_id: UUID) -> list[EvalCase]:
    """Writes the test cases of an agent from its active spec.

    Exists so nobody has to know how to test an LLM; used by the evals API. Reads happen in a short
    transaction, so no connection stays open during the LLM call.

    Args:
        bind: The database handle to read, write and trace through.
        agent_id: The agent to write cases for.

    Returns:
        list[EvalCase]: the stored cases.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If the agent or the generator has no active version.
        AgentConfigurationError: If a spec references an unavailable model or tool.
        AgentNotEvaluableError: If it is a system agent or it was archived.
        CasesAlreadyGeneratedError: If it already has generated cases.
        ProviderError: If the model call fails.
        NoUsableCasesError: If the answer is not a usable set of cases.
    """
    with database_session(bind) as session:
        agent = get_agent(session, agent_id)
        require_evaluable(agent)
        _require_no_generated_cases(session, agent_id)
        execution = load_agent_execution(session, agent_id)
        generator = load_agent_execution(session, CASE_GENERATOR_AGENT_ID)
    payload = _build_generator_input(agent.name, agent.description, execution)
    with SystemAgentRun(RunRecorder(bind), generator, agent.description, RunOrigin.EVAL) as run:
        generated = run.ask(run.initial_messages(payload), GeneratedCases)
        _validate_generated(generated)
        run.finish(generated.model_dump_json())
    cases = _store_generated(bind, agent_id, generated)
    logger.info("Generated %d eval cases for agent %s", len(cases), agent_id)
    return cases
