from datetime import date

import pytest
from pydantic import ValidationError

from bia.rag.artifacts import DocumentDraft, DocumentType


def _values(**changes: object) -> dict[str, object]:
    """Builds the values of a valid document.

    Args:
        changes: The values that differ from the defaults.

    Returns:
        dict[str, object]: the values.
    """
    return {"title": "Doc", "document_type": "faq", "content": "texto", **changes}


def test_validity_can_be_a_single_day() -> None:
    """Verifies the limit of the rule below: the end date is inclusive."""
    day = date(2026, 1, 1)

    draft = DocumentDraft.model_validate(_values(valid_from=day, valid_until=day))

    assert draft.document_type is DocumentType.FAQ


def test_validity_cannot_end_before_it_starts() -> None:
    """Verifies a document that could never be retrieved is rejected when it arrives."""
    with pytest.raises(ValidationError, match="earlier than valid_from"):
        DocumentDraft.model_validate(
            _values(valid_from=date(2026, 2, 1), valid_until=date(2026, 1, 1))
        )


@pytest.mark.parametrize(
    "changes",
    [{"document_type": "contract"}, {"title": ""}, {"content": ""}, {"content": "x" * 200_001}],
)
def test_invalid_documents_are_rejected(changes: dict[str, str]) -> None:
    """Verifies unknown types, empty fields and oversized batches never reach the embedding."""
    with pytest.raises(ValidationError):
        DocumentDraft.model_validate(_values(**changes))
