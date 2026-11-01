from uuid import UUID

from sqlalchemy import Connection

from bia.database.connection import database_session
from bia.rag.artifacts import DocumentDraft, DocumentType, KnowledgeBaseDraft
from bia.rag.repository import insert_knowledge_base

FIRST_SECTION = "A\n\nTexto de A"
SECOND_SECTION = "B\n\nTexto de B"


def new_base(connection: Connection) -> UUID:
    """Creates a knowledge base.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of the base.
    """
    draft = KnowledgeBaseDraft(name="Facturación", description="Tarifas")
    with database_session(connection) as session:
        return insert_knowledge_base(session, draft).id


def build_draft(
    content: str = "# A\nTexto de A\n# B\nTexto de B", **changes: object
) -> DocumentDraft:
    """Builds a tariff document.

    Args:
        content: The markdown.
        changes: The other values that differ from the defaults.

    Returns:
        DocumentDraft: the document.
    """
    return DocumentDraft(
        **{"title": "Tarifas", "document_type": DocumentType.TARIFF, "content": content, **changes}
    )
