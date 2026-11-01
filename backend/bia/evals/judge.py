import json

from bia.builder.system_run import SystemAgentRun
from bia.evals.artifacts import EvalJudgement, EvalVerdict
from bia.evals.config import EVALS_CONFIG
from bia.runtime.execution import AgentExecution
from bia.tracing.artifacts import RunOrigin
from bia.tracing.recorder import RunRecorder

_MAXIMUM_SCORE = 100


class InvalidEvalJudgementError(ValueError):
    """Signals that the eval judge answered something unusable.

    Exists because the structured output guarantees the shape of an answer and not its sense, and
    the gate must not decide on a contradiction. Raised by `judge_answer` and translated to a 502
    by `bia/api/evals.py`.
    """


def _validate_judgement(judgement: EvalJudgement) -> None:
    """Rejects a score out of range, one that contradicts the verdict, or a missing reason.

    Exists because strict structured output accepts no numeric limits, and because a person must be
    able to read why a case failed; used by `judge_answer`.

    Args:
        judgement: The answer of the judge.

    Returns:
        None: the answer is usable.

    Raises:
        InvalidEvalJudgementError: If the answer breaks any of those rules.
    """
    if not 0 <= judgement.score <= _MAXIMUM_SCORE:
        raise InvalidEvalJudgementError(f"The judge gave a score of {judgement.score}")
    reaches_passing_score = judgement.score >= EVALS_CONFIG.passing_score
    if (judgement.verdict is EvalVerdict.PASS) != reaches_passing_score:
        raise InvalidEvalJudgementError(
            f"The judge said {judgement.verdict.value} with a score of {judgement.score}"
        )
    if not judgement.reason.strip():
        raise InvalidEvalJudgementError("The judge gave no reason")


def judge_answer(
    recorder: RunRecorder,
    judge_execution: AgentExecution,
    input_text: str,
    expected_behavior: str,
    answer: str,
) -> EvalJudgement:
    """Decides whether an agent's answer does what was expected, in a traced run of its own.

    Exists as the one judge of test cases and of real runs, so both are measured alike; used by
    `run_evals` and `monitor_agent`.

    Args:
        recorder: Where the trace is written.
        judge_execution: The active version of the eval judge, with its model.
        input_text: What the agent received.
        expected_behavior: What it should have done.
        answer: What it answered.

    Returns:
        EvalJudgement: the checked decision.

    Raises:
        ProviderError: If the model call fails.
        InvalidEvalJudgementError: If the answer of the judge is unusable.
    """
    payload = json.dumps(
        {
            "entrada": input_text,
            "comportamiento_esperado": expected_behavior,
            "respuesta": answer,
            "puntaje_minimo_para_aprobar": EVALS_CONFIG.passing_score,
        },
        ensure_ascii=False,
    )
    with SystemAgentRun(recorder, judge_execution, input_text, RunOrigin.EVAL) as run:
        judgement = run.ask(run.initial_messages(payload), EvalJudgement)
        _validate_judgement(judgement)
        run.finish(judgement.model_dump_json())
    return judgement
