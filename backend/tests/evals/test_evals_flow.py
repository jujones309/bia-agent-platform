from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, func, select, table

from bia.agents import registry as registry_module
from bia.agents.artifacts import AgentDraft, AgentSpec, AgentSpecPatch, AgentStatus
from bia.agents.registry import activate_version, add_version, archive_agent, create_agent
from bia.agents.repository import AgentNotFoundError, get_agent
from bia.builder import system_run
from bia.builder.duplicates.search import find_candidates
from bia.builder.system_agents import (
    CASE_GENERATOR_AGENT_ID,
    EVAL_JUDGE_AGENT_ID,
    sync_system_agents,
)
from bia.catalog.models.artifacts import ModelSize
from bia.catalog.models.repository import list_catalog_models
from bia.catalog.tools.sync import sync_tools
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.evals import runner as runner_module
from bia.evals.artifacts import (
    CaseScope,
    EvalCaseDraft,
    EvalCaseOrigin,
    EvalJudgement,
    EvalVerdict,
    GeneratedCase,
    GeneratedCases,
)
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
    build_report,
    get_report,
    publish_agent,
)
from bia.evals.monitoring import monitor_agent
from bia.evals.repository import EvalCaseNotFoundError, list_cases
from bia.evals.runner import NoEvalCasesError, run_evals
from bia.inventory.repository import list_orchestration_inventory
from bia.providers.base import ProviderError
from bia.tracing.artifacts import RunOrigin, RunStatus
from bia.tracing.repository import list_runs
from tests.builder.duplicates.seed import hide_published_agents
from tests.providers.fake import FakeModelProvider
from tests.runtime.helpers import run_once

_EMBEDDING_DIMENSIONS = 1536
_RESULTS = table("eval_results", column("eval_case_id", Uuid))
_PASS = EvalJudgement(verdict=EvalVerdict.PASS, score=90, reason="Cumple")
_FAIL = EvalJudgement(verdict=EvalVerdict.FAIL, score=10, reason="Inventó el saldo")


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the catalogs and the system agents, rolled back at the end.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
            apply_seeds(session)
            sync_tools(session)
            sync_system_agents(session)
        hide_published_agents(open_connection)
        yield open_connection
        transaction.rollback()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the agent under test, the system agents and the registry.

    Args:
        monkeypatch: The patcher of the modules.

    Returns:
        FakeModelProvider: the provider they will use.
    """
    fake = FakeModelProvider(embedding_dimensions=_EMBEDDING_DIMENSIONS)
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    monkeypatch.setattr(registry_module, "get_provider", lambda _name: fake)
    monkeypatch.setattr(runner_module, "get_provider", lambda _name: fake)
    return fake


def _new_agent(connection: Connection) -> UUID:
    """Creates a draft agent of an employee; requires the `provider` fixture.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of the agent.
    """
    with database_session(connection) as session:
        models = list_catalog_models(session, only_active=True)
    model_id = next(model.id for model in models if model.size is ModelSize.SMALL)
    spec = AgentSpec(purpose="Facturas", system_prompt="Eres útil", model_id=model_id)
    draft = AgentDraft(
        name="Asistente",
        description="Responde dudas de facturas",
        owner_area="Servicio",
        creator="Ana",
        spec=spec,
    )
    return create_agent(connection, draft).agent.id


def _queue_generation(provider: FakeModelProvider, count: int = 10) -> None:
    """Scripts an answer of the generator with the given number of cases.

    Args:
        provider: The provider to script.
        count: How many cases, the last of them out of scope.

    Returns:
        None: the answer is queued.
    """
    scopes = [CaseScope.IN_SCOPE] * (count - 1) + [CaseScope.OUT_OF_SCOPE]
    cases = [
        GeneratedCase(input=f"Pregunta {i}", expected_behavior="Responde", scope=scope)
        for i, scope in enumerate(scopes)
    ]
    provider.queue_structured(GeneratedCases(cases=cases))


def _run_with_verdicts(
    connection: Connection, provider: FakeModelProvider, agent_id: UUID, passes: int, fails: int
) -> None:
    """Runs the evals with scripted answers of the agent and the judge.

    Args:
        connection: The connection of the test's transaction.
        provider: The provider to script.
        agent_id: The agent to evaluate.
        passes: How many cases the judge approves, in order.
        fails: How many it rejects after those.

    Returns:
        None: the results are stored.
    """
    for judgement in [_PASS] * passes + [_FAIL] * fails:
        provider.queue_text("Respuesta")
        provider.queue_structured(judgement)
    run_evals(connection, agent_id)


def _status_of(connection: Connection, agent_id: UUID) -> AgentStatus:
    """Reads the stage of an agent.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent to read.

    Returns:
        AgentStatus: its status.
    """
    with database_session(connection) as session:
        return get_agent(session, agent_id).status


def test_generation_stores_the_cases_and_traces_the_generator(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the cases survive their storage, and generating them reaches the audit."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)

    cases = generate_cases(connection, agent_id)

    assert len(cases) == 10
    assert {case.origin for case in cases} == {EvalCaseOrigin.GENERATED}
    with database_session(connection) as session:
        assert list_cases(session, agent_id) == cases
        run = list_runs(session, CASE_GENERATOR_AGENT_ID, limit=1)[0]
    assert run.origin is RunOrigin.EVAL
    assert run.status is RunStatus.SUCCEEDED
    assert run.total_cost > 0
    assert '"proposito": "Facturas"' in provider.chat_requests[0][1].content


def test_a_second_generation_is_rejected_without_paying_for_it(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies cases cannot pile up; the fake has no second answer to consume."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    generate_cases(connection, agent_id)

    with pytest.raises(CasesAlreadyGeneratedError), connection.begin_nested():
        generate_cases(connection, agent_id)


def test_an_unusable_generation_stores_nothing_and_fails_its_run(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a set too small to measure anything never reaches the gate."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=3)

    with pytest.raises(NoUsableCasesError):
        generate_cases(connection, agent_id)

    with database_session(connection) as session:
        assert list_cases(session, agent_id) == []
        assert list_runs(session, CASE_GENERATOR_AGENT_ID, limit=1)[0].status is RunStatus.FAILED


def test_manual_cases_add_to_the_generated_ones(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a generation is still possible after a manual case, and both count."""
    agent_id = _new_agent(connection)
    draft = EvalCaseDraft(input="¿Y mi reclamo?", expected_behavior="Explica el procedimiento")
    with database_session(connection) as session:
        manual = add_manual_case(session, agent_id, draft)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)

    with database_session(connection) as session:
        cases = list_cases(session, agent_id)

    assert manual.origin is EvalCaseOrigin.MANUAL
    assert len(cases) == 9


def test_manual_case_for_an_unknown_agent_is_a_clear_error(connection: Connection) -> None:
    """Verifies a wrong identifier does not surface as a foreign key failure."""
    draft = EvalCaseDraft(input="Hola", expected_behavior="Saluda")

    with database_session(connection) as session, pytest.raises(AgentNotFoundError):
        add_manual_case(session, uuid4(), draft)


def test_eval_run_on_an_agent_without_cases_is_rejected_and_leaves_it_in_draft(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies running over nothing does not look like progress."""
    agent_id = _new_agent(connection)

    with pytest.raises(NoEvalCasesError), connection.begin_nested():
        run_evals(connection, agent_id)

    assert _status_of(connection, agent_id) is AgentStatus.DRAFT


def test_eval_run_moves_a_draft_to_testing_and_stores_each_result(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the results belong to the version run, with traces under the eval origin."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)

    _run_with_verdicts(connection, provider, agent_id, passes=7, fails=1)

    with database_session(connection) as session:
        report = get_report(session, agent_id)
        agent_runs = list_runs(session, agent_id, limit=50)
        judge_runs = list_runs(session, EVAL_JUDGE_AGENT_ID, limit=8)
    assert _status_of(connection, agent_id) is AgentStatus.TESTING
    assert (report.total_cases, report.passed_cases) == (8, 7)
    assert report.pass_percent == 87.5
    assert report.passes_gate is True
    assert report.outcomes[7].result.judge_reason == "Inventó el saldo"
    assert report.outcomes[7].result.score == 10.0
    assert sum(1 for run in agent_runs if run.origin is RunOrigin.EVAL) == 8
    assert all(run.origin is RunOrigin.EVAL for run in judge_runs)


def test_a_failure_of_the_judge_keeps_the_results_already_obtained(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the paid work is not lost, and what is missing counts against the gate."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    provider.queue_text("Respuesta")
    provider.queue_structured(_PASS)
    provider.queue_text("Respuesta")
    provider.queue_structured(ProviderError("timeout"))

    with pytest.raises(ProviderError):
        run_evals(connection, agent_id)

    with database_session(connection) as session:
        report = build_report(session, agent_id)
    assert report.passed_cases == 1
    assert sum(1 for outcome in report.outcomes if outcome.result is None) == 7
    assert report.passes_gate is False


def test_gate_rejects_below_the_threshold_with_the_failing_cases(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the person learns what to fix, and the agent stays out of the duplicate search."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=7, fails=3)

    with database_session(connection) as session, pytest.raises(PublishRejectedError) as caught:
        publish_agent(session, agent_id)

    rejection = caught.value.rejection
    assert rejection.pass_percent == 70.0
    assert len(rejection.failing_cases) == 3
    assert rejection.failing_cases[0].result.judge_reason == "Inventó el saldo"
    assert _status_of(connection, agent_id) is AgentStatus.TESTING


def test_gate_publishes_at_the_threshold_and_the_agent_becomes_findable(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the end of the builder's flow: only now can reuse find this agent."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=8, fails=2)
    embedding = provider.embed(["Responde dudas de facturas"], "any").embeddings[0]

    with database_session(connection) as session:
        assert find_candidates(session, embedding) == []
        detail = publish_agent(session, agent_id)
        candidates = find_candidates(session, embedding)

    assert detail.agent.status is AgentStatus.PUBLISHED
    assert [candidate.agent_id for candidate in candidates] == [agent_id]


def test_gate_rejects_too_few_cases_even_if_all_of_them_pass(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies one easy manual case cannot open the gate."""
    agent_id = _new_agent(connection)
    draft = EvalCaseDraft(input="Hola", expected_behavior="Saluda")
    with database_session(connection) as session:
        add_manual_case(session, agent_id, draft)
    _run_with_verdicts(connection, provider, agent_id, passes=1, fails=0)

    with database_session(connection) as session:
        report = build_report(session, agent_id)
        with pytest.raises(PublishRejectedError, match="at least 8 cases"):
            publish_agent(session, agent_id)

    assert report.pass_percent == 100.0


def test_a_new_case_counts_against_the_gate_until_it_is_evaluated(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a person cannot publish past a case nobody has run."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=8, fails=0)
    draft = EvalCaseDraft(input="Otro", expected_behavior="Responde")

    with database_session(connection) as session:
        manual = add_manual_case(session, agent_id, draft)
        report = build_report(session, agent_id)

    assert report.total_cases == 9
    assert report.passed_cases == 8
    pending = [outcome.case.id for outcome in report.outcomes if outcome.result is None]
    assert pending == [manual.id]


def test_a_rerun_replaces_what_the_gate_reads(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a fixed flake counts, and that old results do not add up with the new ones."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=0, fails=8)

    _run_with_verdicts(connection, provider, agent_id, passes=8, fails=0)

    with database_session(connection) as session:
        report = build_report(session, agent_id)
    assert report.passed_cases == 8
    assert report.total_cases == 8


def test_editing_a_published_agent_requires_passing_again(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the gap the plan names: an edit cannot reach a published agent untested."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=8, fails=0)
    with database_session(connection) as session:
        publish_agent(session, agent_id)

    with database_session(connection) as session:
        detail = add_version(session, agent_id, AgentSpecPatch(system_prompt="Sé breve"))
        report = build_report(session, agent_id)
        with pytest.raises(PublishRejectedError):
            publish_agent(session, agent_id)

    assert detail.agent.status is AgentStatus.TESTING
    assert report.passed_cases == 0
    assert report.version_number == 2


def test_rolling_back_to_an_approved_version_can_be_published_again_at_no_cost(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies undoing a bad edit needs no new LLM calls; the fake has no answers left."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=8, fails=0)
    with database_session(connection) as session:
        publish_agent(session, agent_id)
        add_version(session, agent_id, AgentSpecPatch(system_prompt="Mala idea"))
        rolled = activate_version(session, agent_id, 1)
        republished = publish_agent(session, agent_id)

    assert rolled.agent.status is AgentStatus.TESTING
    assert republished.agent.status is AgentStatus.PUBLISHED
    assert republished.active_version.version_number == 1


def test_system_agents_cannot_be_published_or_evaluated(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the parts of the platform stay out of the flow."""
    with pytest.raises(AgentNotEvaluableError), connection.begin_nested():
        run_evals(connection, EVAL_JUDGE_AGENT_ID)
    with database_session(connection) as session, pytest.raises(AgentNotEvaluableError):
        publish_agent(session, EVAL_JUDGE_AGENT_ID)


def test_monitor_judges_recent_runs_of_the_origin_against_their_spec(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies only the requested origin is sampled, the newest first, under its version's spec."""
    agent_id = _new_agent(connection)
    for input_text, origin in [
        ("Vieja", RunOrigin.PRODUCTION),
        ("Reciente", RunOrigin.PRODUCTION),
        ("Prueba", RunOrigin.PLAYGROUND),
    ]:
        provider.queue_text("Respuesta")
        run_once(connection, provider, agent_id, input_text, origin)
    provider.queue_structured(_FAIL)

    report = monitor_agent(connection, agent_id, RunOrigin.PRODUCTION, sample_size=1)

    assert [run.input for run in report.runs] == ["Reciente"]
    assert report.pass_percent == 0.0
    assert report.is_drifting is True
    assert report.baseline_pass_percent is None
    assert '\\"proposito\\": \\"Facturas\\"' in provider.chat_requests[-1][1].content
    assert _status_of(connection, agent_id) is AgentStatus.DRAFT


def test_monitor_ignores_runs_without_an_answer(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies nothing is paid for judging a failed run; the fake has no judge answer."""
    agent_id = _new_agent(connection)
    provider.queue_chat_error(ProviderError("timeout"))
    run_once(connection, provider, agent_id, "Pregunta", RunOrigin.PRODUCTION)

    report = monitor_agent(connection, agent_id, RunOrigin.PRODUCTION, sample_size=5)

    assert report.evaluated_runs == 0
    assert report.is_drifting is False


def test_publishing_registers_the_flow_of_the_agent_in_the_same_step(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a newly published agent is visible in the orchestration inventory."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=10, fails=0)

    with database_session(connection) as session:
        before = list_orchestration_inventory(session)
        publish_agent(session, agent_id)
        after = list_orchestration_inventory(session)

    step_agents = [step.agent_id for flow in after for step in flow.steps]
    assert agent_id not in [step.agent_id for flow in before for step in flow.steps]
    assert step_agents.count(agent_id) == 1


def test_a_rejected_publication_registers_no_flow(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies an agent below the gate does not appear as if it were in use."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session, pytest.raises(PublishRejectedError):
        publish_agent(session, agent_id)

    with database_session(connection) as session:
        flows = list_orchestration_inventory(session)
    assert agent_id not in [step.agent_id for flow in flows for step in flow.steps]


def _result_count(connection: Connection, eval_case_id: UUID) -> int:
    """Counts the stored results of a case.

    Args:
        connection: The connection of the test's transaction.
        eval_case_id: The case to look up.

    Returns:
        int: how many results it has.
    """
    query = (
        select(func.count()).select_from(_RESULTS).where(_RESULTS.c.eval_case_id == eval_case_id)
    )
    return connection.execute(query).scalar_one()


def test_a_retired_case_stops_counting_and_keeps_its_results_as_history(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the report and the gate ignore the case while its audit record survives."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=9, fails=1)
    with database_session(connection) as session:
        report = build_report(session, agent_id)
    failing = next(o.case.id for o in report.outcomes if o.result.verdict is EvalVerdict.FAIL)

    with database_session(connection) as session:
        remove_case(session, agent_id, failing)
        report = build_report(session, agent_id)

    assert failing not in [outcome.case.id for outcome in report.outcomes]
    assert (report.passed_cases, report.total_cases) == (9, 9)
    assert _result_count(connection, failing) == 1


def test_retiring_cannot_open_the_gate_below_the_minimum_of_cases(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies removing failures does not let an agent publish with too few cases."""
    agent_id = _new_agent(connection)
    _queue_generation(provider, count=8)
    generate_cases(connection, agent_id)
    _run_with_verdicts(connection, provider, agent_id, passes=7, fails=1)
    with database_session(connection) as session:
        report = build_report(session, agent_id)
    failing = next(o.case.id for o in report.outcomes if o.result.verdict is EvalVerdict.FAIL)

    with database_session(connection) as session:
        remove_case(session, agent_id, failing)
        assert build_report(session, agent_id).total_cases == 7
        with pytest.raises(PublishRejectedError):
            publish_agent(session, agent_id)


def test_retiring_every_generated_case_allows_generating_again(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a bad generated set can be replaced without SQL."""
    agent_id = _new_agent(connection)
    _queue_generation(provider)
    cases = generate_cases(connection, agent_id)
    with database_session(connection) as session:
        for case in cases:
            remove_case(session, agent_id, case.id)

    _queue_generation(provider)
    new_cases = generate_cases(connection, agent_id)

    assert {case.id for case in new_cases}.isdisjoint(case.id for case in cases)


def test_a_case_cannot_be_retired_through_another_agent_or_twice(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a wrong path fails clearly instead of touching another agent's tests."""
    owner_id = _new_agent(connection)
    other_id = _new_agent(connection)
    draft = EvalCaseDraft(input="Hola", expected_behavior="Saluda")
    with database_session(connection) as session:
        case = add_manual_case(session, owner_id, draft)
        with pytest.raises(EvalCaseNotFoundError):
            remove_case(session, other_id, case.id)
        assert [item.id for item in list_cases(session, owner_id)] == [case.id]
        remove_case(session, owner_id, case.id)
        with pytest.raises(EvalCaseNotFoundError):
            remove_case(session, owner_id, case.id)


def test_a_case_of_an_archived_agent_cannot_be_retired(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies an archived agent stays as it was when it left the flow."""
    agent_id = _new_agent(connection)
    draft = EvalCaseDraft(input="Hola", expected_behavior="Saluda")
    with database_session(connection) as session:
        case = add_manual_case(session, agent_id, draft)
        archive_agent(session, agent_id)
        with pytest.raises(AgentNotEvaluableError):
            remove_case(session, agent_id, case.id)
