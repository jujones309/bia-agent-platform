from bia.agents.artifacts import AgentSpec
from bia.providers.artifacts import ChatMessage, MessageRole

_GUARDRAIL_BULLET = "- "
_SECTION_SEPARATOR = "\n\n"
_LINE_SEPARATOR = "\n"


def _build_system_content(spec: AgentSpec) -> str:
    """Joins the system prompt of a spec with its guardrails, as a list.

    Exists so guardrails reach the model inside the instructions it treats as authoritative;
    used by `build_initial_messages`.

    Args:
        spec: The spec being executed.

    Returns:
        str: the content of the system message.
    """
    if not spec.guardrails:
        return spec.system_prompt
    bullets = [f"{_GUARDRAIL_BULLET}{guardrail}" for guardrail in spec.guardrails]
    return f"{spec.system_prompt}{_SECTION_SEPARATOR}{_LINE_SEPARATOR.join(bullets)}"


def build_initial_messages(spec: AgentSpec, input_text: str) -> list[ChatMessage]:
    """Builds the conversation an execution starts from.

    Exists to keep the assembly apart from the tool-calling loop; used by `AgentRunner`.

    Args:
        spec: The spec being executed.
        input_text: What the user asked.

    Returns:
        list[ChatMessage]: the system message followed by the user message.
    """
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=_build_system_content(spec)),
        ChatMessage(role=MessageRole.USER, content=input_text),
    ]
