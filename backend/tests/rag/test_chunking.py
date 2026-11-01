from pathlib import Path

import pytest

from bia.rag.artifacts import DocumentDraft, DocumentType
from bia.rag.chunking import InvalidDocumentError, chunk_document

_KNOWLEDGE_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "knowledge"


def _draft(document_type: DocumentType, content: str) -> DocumentDraft:
    """Builds a document.

    Args:
        document_type: The type, which selects the strategy.
        content: The markdown.

    Returns:
        DocumentDraft: the document, titled "Doc".
    """
    return DocumentDraft(title="Doc", document_type=document_type, content=content)


@pytest.mark.parametrize("document_type", [DocumentType.TARIFF, DocumentType.PROCEDURE])
def test_sections_keep_the_path_of_headings_above_them(document_type: DocumentType) -> None:
    """Verifies a subsection is understandable alone, and a sibling closes the previous path."""
    content = "# Tarifas\n\n## Hogar\nValor A\n\n### Subsidio\nValor B\n\n## Comercio\nValor C\n"

    chunks = chunk_document(_draft(document_type, content))

    assert [chunk.metadata.section for chunk in chunks] == [
        "Tarifas > Hogar",
        "Tarifas > Hogar > Subsidio",
        "Tarifas > Comercio",
    ]
    assert chunks[1].content == "Tarifas > Hogar > Subsidio\n\nValor B"
    assert all(chunk.metadata.document == "Doc" for chunk in chunks)


def test_a_table_stays_whole_inside_its_section() -> None:
    """Verifies a tariff row is never separated from the header that gives it meaning."""
    content = "## Hogar\n| Estrato | Valor |\n|---|---|\n| 1 | 412 |\n| 2 | 515 |\n"

    chunks = chunk_document(_draft(DocumentType.TARIFF, content))

    assert len(chunks) == 1
    assert "| Estrato | Valor |\n|---|---|\n| 1 | 412 |\n| 2 | 515 |" in chunks[0].content


def test_text_before_the_first_heading_is_cited_with_the_document_title() -> None:
    """Verifies an introduction is not lost and still has a source to cite."""
    chunks = chunk_document(_draft(DocumentType.PROCEDURE, "Introducción\n\n# Tema\nDetalle"))

    assert [chunk.metadata.section for chunk in chunks] == ["Doc", "Tema"]


def test_faq_makes_one_chunk_per_question_without_its_categories() -> None:
    """Verifies each answer travels with its question and the citation is the question."""
    content = "# FAQ\n\n## Pagos\n\n### ¿Dónde pago?\nEn la app.\n\n### ¿Hay mora?\nSí, 1,8 %.\n"

    chunks = chunk_document(_draft(DocumentType.FAQ, content))

    assert [chunk.metadata.section for chunk in chunks] == ["¿Dónde pago?", "¿Hay mora?"]
    assert chunks[0].content == "¿Dónde pago?\n\nEn la app."


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("# FAQ\nIntroducción\n\n## ¿Pregunta?\nRespuesta", "under 'FAQ'"),
        ("Texto suelto\n\n## ¿Pregunta?\nRespuesta", "under 'Doc'"),
        ("## ¿Pregunta sin respuesta?\n\n## ¿Otra?\nRespuesta", "has no answer"),
    ],
)
def test_faq_rejects_content_it_would_lose(content: str, expected: str) -> None:
    """Verifies malformed text stops the ingestion instead of disappearing from the base."""
    with pytest.raises(InvalidDocumentError, match=expected):
        chunk_document(_draft(DocumentType.FAQ, content))


@pytest.mark.parametrize("document_type", list(DocumentType))
def test_a_document_without_text_is_rejected(document_type: DocumentType) -> None:
    """Verifies every strategy refuses to produce an empty batch for the embedding call."""
    with pytest.raises(InvalidDocumentError, match="no text"):
        chunk_document(_draft(document_type, "# Solo un título\n\n## Y otro\n"))


def test_a_section_too_long_to_embed_is_rejected_naming_it() -> None:
    """Verifies the failure tells what to divide, instead of an opaque provider error."""
    with pytest.raises(InvalidDocumentError, match="'Larga'.*divide it"):
        chunk_document(_draft(DocumentType.TARIFF, "# Larga\n" + "x" * 8000))


@pytest.mark.parametrize(
    ("file_name", "document_type", "expected_section"),
    [
        ("tarifas.md", DocumentType.TARIFF, "Tarifas de energía 2026 > Tarifa industrial"),
        (
            "procedimientos-facturacion.md",
            DocumentType.PROCEDURE,
            "Procedimientos de facturación > Presentar un reclamo por la factura",
        ),
        ("preguntas-frecuentes.md", DocumentType.FAQ, "¿Qué significa un saldo negativo?"),
    ],
)
def test_the_real_documents_can_be_divided(
    file_name: str, document_type: DocumentType, expected_section: str
) -> None:
    """Verifies the knowledge of the demo follows the rules of its strategy."""
    content = (_KNOWLEDGE_DIRECTORY / file_name).read_text(encoding="utf-8")

    chunks = chunk_document(_draft(document_type, content))

    assert expected_section in [chunk.metadata.section for chunk in chunks]
