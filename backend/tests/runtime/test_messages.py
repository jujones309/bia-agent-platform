from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from bia.agents.artifacts import AgentSpec
from bia.providers.artifacts import ChatMessage, MessageRole, ToolCall
from bia.runtime.messages import build_follow_up_messages, build_initial_messages
from bia.tracing.artifacts import RunStepRecord, StepType

_SPEC = AgentSpec(purpose="p", system_prompt="Eres útil", model_id=uuid4())


def _llm_step(
    received: list[ChatMessage], reply: ChatMessage | None, error: str | None = None
) -> RunStepRecord:
    """Builds the recorded step of a model call.

    Args:
        received: What the model received.
        reply: What it replied, or None if the call failed.
        error: Why the call failed.

    Returns:
        RunStepRecord: the step, as the trace returns it.
    """
    return RunStepRecord(
        id=uuid4(),
        run_id=uuid4(),
        step_order=1,
        step_type=StepType.LLM_CALL,
        model_id=uuid4(),
        tool_id=None,
        input=[message.model_dump(mode="json") for message in received],
        output=reply.model_dump(mode="json") if reply else None,
        input_tokens=0,
        output_tokens=0,
        cost=Decimal(0),
        latency_ms=1,
        error=error,
        created_at=datetime.now(UTC),
    )


def test_messages_carry_the_system_prompt_and_the_input_in_order() -> None:
    """Verifies the conversation starts with the instructions, unaltered without guardrails."""
    spec = AgentSpec(purpose="p", system_prompt="Eres útil", model_id=uuid4())

    system, user = build_initial_messages(spec, "¿Mi saldo?")

    assert (system.role, system.content) == (MessageRole.SYSTEM, "Eres útil")
    assert (user.role, user.content) == (MessageRole.USER, "¿Mi saldo?")


def test_guardrails_are_part_of_the_system_message() -> None:
    """Verifies guardrails reach the model, and never through the user's message."""
    spec = AgentSpec(
        purpose="p",
        system_prompt="Eres útil",
        model_id=uuid4(),
        guardrails=["No des asesoría legal", "No inventes saldos"],
    )

    system, user = build_initial_messages(spec, "hola")

    assert system.content == "Eres útil\n\n- No des asesoría legal\n- No inventes saldos"
    assert user.content == "hola"


def test_follow_up_remembers_the_latest_answer_and_ends_with_the_new_message() -> None:
    """Verifies the history comes from the trace, so the model can answer a follow-up question."""
    first = build_initial_messages(_SPEC, "¿Saldo?")
    answer = ChatMessage(role=MessageRole.ASSISTANT, content="100")

    messages = build_follow_up_messages(_SPEC, [_llm_step(first, answer)], "¿Y en dólares?")

    assert messages == [
        *first,
        answer,
        ChatMessage(role=MessageRole.USER, content="¿Y en dólares?"),
    ]


def test_follow_up_leaves_out_turns_that_got_no_answer() -> None:
    """Verifies unanswered tool calls of a failed turn never reach the model, which rejects them."""
    first = build_initial_messages(_SPEC, "¿Saldo?")
    answer = ChatMessage(role=MessageRole.ASSISTANT, content="100")
    second = [*first, answer, ChatMessage(role=MessageRole.USER, content="Otra")]
    requests_tool = ChatMessage(
        role=MessageRole.ASSISTANT, tool_calls=[ToolCall(id="c1", name="t", arguments="{}")]
    )
    steps = [_llm_step(first, answer), _llm_step(second, requests_tool)]

    messages = build_follow_up_messages(_SPEC, steps, "Reintento")

    assert [message.content for message in messages[1:]] == ["¿Saldo?", "100", "Reintento"]


def test_follow_up_starts_over_when_no_turn_got_an_answer() -> None:
    """Verifies a conversation whose first turn failed still has its instructions."""
    failed = _llm_step(build_initial_messages(_SPEC, "¿Saldo?"), None, "timeout")

    system, user = build_follow_up_messages(_SPEC, [failed], "Reintento")

    assert (system.content, user.content) == ("Eres útil", "Reintento")
