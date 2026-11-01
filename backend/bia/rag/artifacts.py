from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bia.providers.artifacts import TokenUsage

DEFAULT_TOP_K = 5
MAX_TOP_K = 20
_MAX_DOCUMENT_CHARACTERS = 200_000  # keeps a whole document inside one embedding request


class DocumentType(StrEnum):
    """The kinds of document a knowledge base can hold.

    Exists to mirror the `document_type` check of the `knowledge_documents` table, and because
    the type defines the chunking strategy; consumed by `bia/rag/chunking.py`.
    """

    TARIFF = "tariff"
    PROCEDURE = "procedure"
    FAQ = "faq"  # each chunk is one question with its answer


class KnowledgeBaseDraft(BaseModel):
    """Describes a knowledge base to be created.

    Exists as the body of `POST /knowledge-bases`; consumed by `insert_knowledge_base`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class KnowledgeBase(BaseModel):
    """Represents a knowledge base agents can retrieve from.

    Exists as the contract of a row of the `knowledge_bases` table; returned by the repository
    and by the knowledge API.
    """

    id: UUID
    name: str
    description: str
    created_at: datetime


class DocumentDraft(BaseModel):
    """Describes a document to be ingested, with its full text.

    Exists as the body of `POST /knowledge-bases/{id}/ingest`. The text travels in the request
    because the deployed backend has no access to the files of the repository. Consumed by
    `ingest_document`.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)  # identifies the document inside its base when re-ingesting
    document_type: DocumentType
    content: str = Field(min_length=1, max_length=_MAX_DOCUMENT_CHARACTERS)  # markdown
    valid_from: date | None = None
    valid_until: date | None = None  # inclusive; retrieval ignores the document after this date

    @model_validator(mode="after")
    def _require_ordered_validity(self) -> Self:
        """Rejects a validity period that ends before it starts.

        Exists because such a document could never be retrieved, and nothing else would say
        why; called by pydantic on construction.

        Returns:
            Self: the validated draft.
        """
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot be earlier than valid_from")
        return self


class ChunkMetadata(BaseModel):
    """Holds what an agent needs to cite a fragment.

    Exists as the contract of `knowledge_chunks.metadata`; written by the chunking and read
    back by the search.
    """

    document: str
    section: str


class DocumentChunk(BaseModel):
    """Describes a retrievable fragment of a document, before it is embedded.

    Exists as the output of `chunk_document`; consumed by `ingest_document`.
    """

    content: str
    metadata: ChunkMetadata


class RetrievedChunk(BaseModel):
    """Describes a fragment returned by a search, with its source.

    Exists so answers can cite where they come from; produced by `search_chunks` and consumed
    by the knowledge API and `buscar_conocimiento`, which also stores it in the trace.
    """

    chunk_id: UUID
    document: str
    section: str
    content: str
    similarity: float  # cosine similarity: higher means closer to the query


class KnowledgeSearchResult(BaseModel):
    """Holds the fragments of a search and what embedding its query cost.

    Exists so each caller can account for the call: the tool records it as a run step, and the
    API, which has no run to record it in, returns it. Produced by `search_knowledge`.
    """

    chunks: list[RetrievedChunk]  # closest first
    model_id: UUID  # the embedding model of the query
    usage: TokenUsage
    cost: Decimal
    latency_ms: int = Field(ge=0)  # of the embedding call only


class IngestionResult(BaseModel):
    """Summarizes the ingestion of one document.

    Exists as the contract of `POST /knowledge-bases/{id}/ingest`, which has no run to record
    its spending in; produced by `ingest_document`.
    """

    document_id: UUID
    chunks_ingested: int
    model_id: UUID  # the embedding model used
    usage: TokenUsage
    cost: Decimal
    latency_ms: int = Field(ge=0)  # of the embedding call only
