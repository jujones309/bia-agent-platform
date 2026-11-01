from uuid import uuid4

from bia.agents.artifacts import AgentSpec
from bia.providers.artifacts import MessageRole
from bia.runtime.messages import build_initial_messages


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
