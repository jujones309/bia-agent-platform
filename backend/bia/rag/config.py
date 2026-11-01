from pydantic import BaseModel, ConfigDict, Field


class RagConfig(BaseModel):
    """Holds the numbers that decide what a knowledge search returns.

    Exists to keep the calibration of retrieval in one place; consumed through `RAG_CONFIG` by
    `bia/rag/retrieval.py`.
    """

    model_config = ConfigDict(frozen=True)

    # Calibrated for the embedding model of the catalog: changing that model requires calibrating
    # again. The README has the measurements.
    minimum_similarity: float = Field(default=0.35, ge=-1, le=1)
    # Up to this size, a base is compared exactly: the vector index loses fragments of small bases.
    exact_search_maximum_chunks: int = Field(default=20_000, ge=0)


RAG_CONFIG = RagConfig()
