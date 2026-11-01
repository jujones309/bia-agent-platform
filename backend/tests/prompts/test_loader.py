from pathlib import Path

import pytest

from bia.prompts import loader
from bia.prompts.loader import (
    InvalidPromptFileError,
    PromptFileNotFoundError,
    PromptName,
    PromptVertical,
    load_prompt,
)


def _write_prompt(root: Path, monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    """Writes the judge's prompt file under a temporary package directory.

    Args:
        root: The directory that replaces the package.
        monkeypatch: The patcher of the loader.
        content: The content of the file.

    Returns:
        None: the file is written and the loader points at it.
    """
    directory = root / PromptVertical.BUILDER_DUPLICATES / "prompts"
    directory.mkdir(parents=True)
    (directory / f"{PromptName.JUDGE}.md").write_text(content, encoding="utf-8")
    monkeypatch.setattr(loader, "_PACKAGE_DIRECTORY", root)


def test_load_prompt_leaves_the_documenting_comment_out_of_the_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the model receives the instructions and not the notes for maintainers."""
    _write_prompt(tmp_path, monkeypatch, "<!-- why it exists -->\n\nEres un juez.\n")

    assert load_prompt(PromptVertical.BUILDER_DUPLICATES, PromptName.JUDGE) == "Eres un juez."


def test_load_prompt_only_strips_the_opening_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a later comment, which belongs to the prompt's text, is not lost."""
    _write_prompt(tmp_path, monkeypatch, "<!-- why -->\nAntes <!-- nota --> después")

    prompt = load_prompt(PromptVertical.BUILDER_DUPLICATES, PromptName.JUDGE)

    assert prompt == "Antes <!-- nota --> después"


@pytest.mark.parametrize(
    "content", ["Eres un juez.", "<!-- never closed\nEres un juez.", "<!-- only a comment -->\n"]
)
def test_load_prompt_rejects_a_file_without_comment_or_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    """Verifies an undocumented or empty prompt fails instead of reaching a model."""
    _write_prompt(tmp_path, monkeypatch, content)

    with pytest.raises(InvalidPromptFileError, match="judge.md"):
        load_prompt(PromptVertical.BUILDER_DUPLICATES, PromptName.JUDGE)


def test_load_prompt_names_vertical_and_prompt_when_the_file_is_missing() -> None:
    """Verifies the error says what to create; the designer's directory has no judge."""
    with pytest.raises(PromptFileNotFoundError, match="'builder/designer' has no prompt 'judge'"):
        load_prompt(PromptVertical.BUILDER_DESIGNER, PromptName.JUDGE)


@pytest.mark.parametrize(
    ("vertical", "name", "expected"),
    [
        (PromptVertical.BUILDER_DUPLICATES, PromptName.JUDGE, "candidate_agent_id"),
        (PromptVertical.BUILDER_DESIGNER, PromptName.DESIGNER, "problemas_de_validacion"),
    ],
)
def test_real_prompts_load_and_describe_their_contract(
    vertical: PromptVertical, name: PromptName, expected: str
) -> None:
    """Verifies the shipped prompts follow the conventions and mention what the code relies on."""
    prompt = load_prompt(vertical, name)

    assert expected in prompt
    assert "Consumed by" not in prompt
