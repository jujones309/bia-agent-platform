import re
from collections.abc import Callable
from dataclasses import dataclass

from bia.rag.artifacts import ChunkMetadata, DocumentChunk, DocumentDraft, DocumentType

_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_MAX_CHUNK_CHARACTERS = 8000  # well below the input limit of the embedding models
_QUESTION_MARK = "?"
_SECTION_PATH_SEPARATOR = " > "


class InvalidDocumentError(ValueError):
    """Signals that a document cannot be divided into chunks.

    Exists so bad content fails before anything is spent or written, saying what to fix. Raised
    by `chunk_document` and translated to a 422 by `bia/api/rag.py`.
    """


@dataclass(frozen=True)
class _Section:
    """Holds the text under one markdown heading, with the headings above it.

    Exists to share the parsing between the chunking strategies; built by `_split_sections`.
    """

    heading_path: tuple[str, ...]  # empty for the text before the first heading
    body: str


def _split_sections(content: str) -> list[_Section]:
    """Divides markdown into the text under each heading.

    Exists because every strategy works on sections. A subsection only keeps the headings of a
    higher level, so a new heading closes the previous ones at its level and below.

    Args:
        content: The markdown of the document.

    Returns:
        list[_Section]: the sections in order, including those without a body.
    """
    sections = []
    open_headings: list[tuple[int, str]] = []
    body_lines: list[str] = []
    for line in content.splitlines():
        match = _HEADING_PATTERN.match(line)
        if match is None:
            body_lines.append(line)
            continue
        sections.append(_build_section(open_headings, body_lines))
        level = len(match[1])
        open_headings = [heading for heading in open_headings if heading[0] < level]
        open_headings.append((level, match[2]))
        body_lines = []
    sections.append(_build_section(open_headings, body_lines))
    return sections


def _build_section(open_headings: list[tuple[int, str]], body_lines: list[str]) -> _Section:
    """Closes the section being read.

    Exists to keep `_split_sections` focused on walking the lines.

    Args:
        open_headings: The level and text of the headings above the section.
        body_lines: The lines under the last heading.

    Returns:
        _Section: the section, with its body stripped.
    """
    return _Section(tuple(text for _, text in open_headings), "\n".join(body_lines).strip())


def _chunk_by_headings(draft: DocumentDraft) -> list[DocumentChunk]:
    """Makes one chunk per section that has text, keeping tables and steps whole.

    Exists for tariffs and procedures, whose meaning depends on the section they are in: the
    heading path goes inside the content so it also counts in the embedding.

    Args:
        draft: The document to divide.

    Returns:
        list[DocumentChunk]: one chunk per section with a body.
    """
    chunks = []
    for section in _split_sections(draft.content):
        if not section.body:
            continue
        label = _SECTION_PATH_SEPARATOR.join(section.heading_path) or draft.title
        chunks.append(_build_chunk(draft.title, label, section.body))
    return chunks


def _chunk_by_question(draft: DocumentDraft) -> list[DocumentChunk]:
    """Makes one chunk per question and answer.

    Exists because a FAQ answer is only meaningful next to its question. Headings that are not
    questions may group them, but text under them is an error, since it would be lost silently.

    Args:
        draft: The document to divide, whose questions are headings ending in a question mark.

    Returns:
        list[DocumentChunk]: one chunk per question.

    Raises:
        InvalidDocumentError: If a question has no answer or text is outside of a question.
    """
    chunks = []
    for section in _split_sections(draft.content):
        heading = section.heading_path[-1] if section.heading_path else draft.title
        if heading.endswith(_QUESTION_MARK):
            if not section.body:
                raise InvalidDocumentError(f"The question '{heading}' has no answer")
            chunks.append(_build_chunk(draft.title, heading, section.body))
        elif section.body:
            raise InvalidDocumentError(f"The text under '{heading}' does not belong to a question")
    return chunks


def _build_chunk(document_title: str, label: str, body: str) -> DocumentChunk:
    """Builds a chunk whose content starts with what the text is about.

    Exists so both strategies produce the same shape; used by the strategies above.

    Args:
        document_title: The title of the document, to cite it.
        label: The section or question, to cite it and to embed it with the text.
        body: The text of the section.

    Returns:
        DocumentChunk: the chunk.

    Raises:
        InvalidDocumentError: If the chunk is too long to be embedded usefully.
    """
    content = f"{label}\n\n{body}"
    if len(content) > _MAX_CHUNK_CHARACTERS:
        raise InvalidDocumentError(
            f"The section '{label}' has {len(content)} characters and the limit is "
            f"{_MAX_CHUNK_CHARACTERS}; divide it with headings"
        )
    return DocumentChunk(
        content=content, metadata=ChunkMetadata(document=document_title, section=label)
    )


_STRATEGIES: dict[DocumentType, Callable[[DocumentDraft], list[DocumentChunk]]] = {
    DocumentType.TARIFF: _chunk_by_headings,
    DocumentType.PROCEDURE: _chunk_by_headings,
    DocumentType.FAQ: _chunk_by_question,
}


def chunk_document(draft: DocumentDraft) -> list[DocumentChunk]:
    """Divides a document into retrievable chunks, following the strategy of its type.

    Exists as the single entrance to chunking; used by `ingest_document`.

    Args:
        draft: The document to divide.

    Returns:
        list[DocumentChunk]: at least one chunk, in the order of the document.

    Raises:
        InvalidDocumentError: If the document yields no chunks or breaks a rule of its strategy.
    """
    chunks = _STRATEGIES[draft.document_type](draft)
    if not chunks:
        raise InvalidDocumentError(f"The document '{draft.title}' has no text to retrieve")
    return chunks
