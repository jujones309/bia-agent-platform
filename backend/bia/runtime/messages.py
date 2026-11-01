from bia.agents.artifacts import AgentSpec
from bia.providers.artifacts import ChatMessage, MessageRole
from bia.tracing.artifacts import RunStepRecord, StepType

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


def _restore_answered_history(steps: list[RunStepRecord]) -> list[ChatMessage] | None:
    """Rebuilds a conversation up to its latest answer from the trace of its run.

    Exists because each model call stores everything it received, so the trace already holds the
    history, tool calls included. Turns after that answer failed: they are left out, since they
    may have ended with tool calls that nothing answered, which the model would reject. Used by
    `build_follow_up_messages`.

    Args:
        steps: The steps of the run, in execution order.

    Returns:
        list[ChatMessage] | None: the messages up to the latest answer, or None without answers.
    """
    for step in reversed(steps):
        if step.step_type is not StepType.LLM_CALL or step.output is None:
            continue
        reply = ChatMessage.model_validate(step.output)
        if not reply.tool_calls:
            return [ChatMessage.model_validate(message) for message in step.input] + [reply]
    return None


def build_follow_up_messages(
    spec: AgentSpec, steps: list[RunStepRecord], input_text: str
) -> list[ChatMessage]:
    """Builds the conversation a later turn starts from, so the agent remembers the earlier ones.

    Exists to give an open run its memory; used by `bia/runtime/conversations.py`.

    Args:
        spec: The spec the run executes.
        steps: The steps recorded in the run so far, in execution order.
        input_text: The new message of the user.

    Returns:
        list[ChatMessage]: the history followed by the new user message; only the system and user
            messages if no earlier turn got an answer.
    """
    history = _restore_answered_history(steps)
    if history is None:
        return build_initial_messages(spec, input_text)
    return [*history, ChatMessage(role=MessageRole.USER, content=input_text)]
