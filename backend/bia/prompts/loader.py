from enum import StrEnum
from pathlib import Path

_PACKAGE_DIRECTORY = Path(__file__).resolve().parent.parent
_PROMPTS_DIRECTORY_NAME = "prompts"
_PROMPT_SUFFIX = ".md"
_COMMENT_OPENING = "<!--"
_COMMENT_CLOSING = "-->"


class PromptVertical(StrEnum):
    """The parts of the platform that own prompt files, named after their directory.

    Exists so prompts are addressed through a closed set; consumed by `load_prompt`. Each
    vertical that adds a `prompts/` directory adds its member here.
    """

    BUILDER_DUPLICATES = "builder/duplicates"
    BUILDER_DESIGNER = "builder/designer"


class PromptName(StrEnum):
    """The prompt files of the platform, named after the file they map to.

    Exists so callers cannot misspell a file name; consumed by `load_prompt`.
    """

    JUDGE = "judge"
    DESIGNER = "designer"


class PromptFileNotFoundError(FileNotFoundError):
    """Signals that a vertical does not have the requested prompt file.

    Exists to name the missing vertical and prompt instead of a bare path. Raised by
    `load_prompt`.
    """


class InvalidPromptFileError(ValueError):
    """Signals that a prompt file does not open with the comment that documents it.

    Exists because every prompt must explain why it exists and where it is consumed. Raised by
    `load_prompt`.
    """


def _strip_opening_comment(content: str, path: Path) -> str:
    """Removes the comment a prompt file opens with.

    Exists because the comment documents the file for its readers and must not reach the model;
    used by `load_prompt`.

    Args:
        content: The content of the file.
        path: The file, to name it if it is invalid.

    Returns:
        str: the text of the prompt, without surrounding whitespace.

    Raises:
        InvalidPromptFileError: If the file does not open with a closed comment or has no text.
    """
    closing_position = content.find(_COMMENT_CLOSING)
    if not content.startswith(_COMMENT_OPENING) or closing_position == -1:
        raise InvalidPromptFileError(f"The prompt file {path} must open with a comment")
    prompt = content[closing_position + len(_COMMENT_CLOSING) :].strip()
    if not prompt:
        raise InvalidPromptFileError(f"The prompt file {path} has no text after its comment")
    return prompt


def load_prompt(vertical: PromptVertical, name: PromptName) -> str:
    """Reads a platform prompt, ready to be sent to a model.

    Exists because prompts live in `.md` files and never in Python strings; used by every
    vertical that owns a prompt.

    Args:
        vertical: The vertical whose `prompts/` directory holds the file.
        name: The prompt that names the file.

    Returns:
        str: the text of the prompt, without its opening comment.

    Raises:
        PromptFileNotFoundError: If the vertical has no such prompt.
        InvalidPromptFileError: If the file does not follow the prompt conventions.
    """
    path = _PACKAGE_DIRECTORY / vertical / _PROMPTS_DIRECTORY_NAME / f"{name}{_PROMPT_SUFFIX}"
    if not path.is_file():
        raise PromptFileNotFoundError(f"'{vertical}' has no prompt '{name}' at {path}")
    return _strip_opening_comment(path.read_text(encoding="utf-8"), path)
